from random import randint
import sys, traceback, threading, socket

from VideoStream import VideoStream
from RtpPacket import RtpPacket

_TIME_WAIT_ = 0.04

class ServerWorker:
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'
    
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2
    
    clientInfo = {}
    
    # Maximum RTP payload size for each UDP datagram (safe for typical MTU)
    MAX_RTP_PAYLOAD = 1400
    # Custom fragment header size: 4 bytes frameId + 1 byte last-flag
    FRAG_HDR_SIZE = 5
    
    def __init__(self, clientInfo):
        self.clientInfo = clientInfo
        
    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()
    
    def recvRtspRequest(self):
        """Receive RTSP request from the client."""
        connSocket = self.clientInfo['rtspSocket'][0]
        while True:
            try:            
                data = connSocket.recv(4096)
                if data:
                    print("Data received:\n" + data.decode("utf-8"))
                    self.processRtspRequest(data.decode("utf-8"))
                else:
                    print("Client disconnected\n")
                    break
            except Exception as e:
                print(f"Socket error: {e}")
                break
        if 'rtspSocket' in self.clientInfo:
            try:
                self.clientInfo['rtspSocket'][0].close()
            except:
                pass
            
            
    def processRtspRequest(self, data):
        """Process RTSP request sent from the client."""
        lines = data.splitlines()
        if not lines:
            return
        
        # Parse request line
        line1 = lines[0].split(' ')
        requestType = line1[0]
        filename = line1[1] if len(line1) > 1 else ""
        
        # Find headers
        seq = None
        transport_line = None
        start_frame = None
        
        for line in lines[1:]:
            line = line.strip()
            
            if line.lower().startswith("cseq"):
                parts = line.split(':', 1)
                
                if len(parts) > 1:
                    seq = parts[1].strip()
            elif line.lower().startswith("transport"):
                transport_line = line
            elif line.lower().startswith("start-frame"):
                parts = line.split(':', 1)
                if len(parts) > 1:
                    try:
                        start_frame = int(parts[1].strip())
                    except:
                        start_frame = None
        
        if requestType == self.SETUP:
            if self.state == self.INIT:
                print("processing SETUP")
                try:
                    self.clientInfo['videoStream'] = VideoStream(filename)
                    
                    if start_frame is not None and start_frame > 1:
                        self.clientInfo['videoStream'].seek(start_frame - 1)
                        
                    self.state = self.READY
                    
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq if seq else "0")
                    return
                
                self.clientInfo['session'] = randint(100000, 999999)
                
                # parse client_port robustly
                if transport_line:
                    try:
                        parts = transport_line.split('client_port=')
                        if len(parts) > 1:
                            port_str = parts[1].split(';')[0].strip()
                            port_num = int(''.join(ch for ch in port_str if ch.isdigit()))
                            
                            self.clientInfo['rtpPort'] = port_num
                    except Exception:
                        print("Warning: failed to parse Transport header:", transport_line)
                # fallback attempt
                if 'rtpPort' not in self.clientInfo:
                    try:
                        tokens = lines[2].split()
                        for t in tokens:
                            if t.isdigit():
                                self.clientInfo['rtpPort'] = int(t)
                                break
                    except Exception:
                        pass

                print("SETUP complete: session=", self.clientInfo.get('session'),
                      "rtpPort=", self.clientInfo.get('rtpPort'))
                
                self.replyRtsp(self.OK_200, seq if seq else "0", self.clientInfo['videoStream'].getTotalFrames())
        
        elif requestType == self.PLAY:
            if self.state == self.READY:
                print("processing PLAY")
                self.state = self.PLAYING
                self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                
                # initialize a packet sequence counter for RTP packets
                self.clientInfo.setdefault('rtpPacketSeq', 0)
                self.replyRtsp(self.OK_200, seq if seq else "0")
                
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
                self.clientInfo['worker'].start()
        
        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                print("processing PAUSE")
                self.state = self.READY
                
                if 'event' in self.clientInfo:
                    self.clientInfo['event'].set()
                    
                self.replyRtsp(self.OK_200, seq if seq else "0")
        
        elif requestType == self.TEARDOWN:
            print("processing TEARDOWN")
            if 'event' in self.clientInfo:
                self.clientInfo['event'].set()

            self.replyRtsp(self.OK_200, seq if seq else "0")
            
            if 'rtpSocket' in self.clientInfo:
                try:
                    self.clientInfo['rtpSocket']
                except:
                    pass
                
    def sendRtp(self):
        """Send RTP packets over UDP with fragmentation when needed."""
        while True:
            if 'event' in self.clientInfo:
                self.clientInfo['event'].wait(_TIME_WAIT_)
            if 'event' in self.clientInfo and self.clientInfo['event'].isSet(): 
                break 
                
            data = self.clientInfo['videoStream'].nextFrame()
            
            if not data:
                print("sendRtp: no frame data (videoStream.nextFrame() returned None). Stopping sender.")
                if 'event' in self.clientInfo:
                    self.clientInfo['event'].set()
                break

            frameNumber = self.clientInfo['videoStream'].frameNbr()
            
            try:
                address = self.clientInfo['rtspSocket'][1][0]
                port = int(self.clientInfo.get('rtpPort', 0))
                
                if port == 0:
                    raise ValueError("rtpPort not set or zero")
            except Exception as e:
                print("Connection Error preparing send target:", e)
                if 'event' in self.clientInfo:
                    self.clientInfo['event'].set()
                break

            # Fragmentation logic
            max_payload = self.MAX_RTP_PAYLOAD - self.FRAG_HDR_SIZE
            total_len = len(data)
            
            if total_len <= max_payload:
                # single packet: prefix with frameId+lastflag(1)
                frag_payload = frameNumber.to_bytes(4, 'big') + bytes([1]) + data
                # increment packet seq
                self.clientInfo['rtpPacketSeq'] += 1
                seqnum = self.clientInfo['rtpPacketSeq']
                
                try:
                    print(f"sendRtp: sending single packet frame {frameNumber} ({len(data)} bytes) to {address}:{port}")
                    self.clientInfo['rtpSocket'].sendto(self.makeRtp(frag_payload, seqnum),(address,port))
                except Exception as e:
                    print("Connection Error while sending RTP (single):", e)
                    traceback.print_exc()
                    if 'event' in self.clientInfo:
                        self.clientInfo['event'].set()
                    break
            else:
                # multiple fragments
                offset = 0
                frag_index = 0
                
                while offset < total_len:
                    chunk = data[offset:offset+max_payload]
                    offset += len(chunk)
                    is_last = 1 if offset >= total_len else 0
                    frag_payload = frameNumber.to_bytes(4, 'big') + bytes([is_last]) + chunk
                    
                    self.clientInfo['rtpPacketSeq'] += 1
                    seqnum = self.clientInfo['rtpPacketSeq']
                    
                    try:
                        print(f"sendRtp: sending fragment {frag_index} (len {len(chunk)}) for frame {frameNumber} to {address}:{port}")
                        self.clientInfo['rtpSocket'].sendto(self.makeRtp(frag_payload, seqnum),(address,port))
                    except Exception as e:
                        print("Connection Error while sending RTP (fragment):", e)
                        traceback.print_exc()
                        if 'event' in self.clientInfo:
                            self.clientInfo['event'].set()
                        return
                    frag_index += 1

    def makeRtp(self, payload, seqnum):
        """RTP-packetize the video data. seqnum is an increasing packet sequence number."""
        version = 2
        padding = 0
        extension = 0
        cc = 0
        marker = 0
        pt = 26 # MJPEG type
        ssrc = 0 
        
        rtpPacket = RtpPacket()
        # we pass seqnum (packet sequence)
        rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
        return rtpPacket.getPacket()
        
    def replyRtsp(self, code, seq, totalFr = None):
        """Send RTSP reply to the client."""
        if code == self.OK_200:
            reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session']) + '\n'
            # add total frame when initialize
            if totalFr is not None:
                reply += "FrameNbr: " + str(totalFr) + '\n'
            reply += '\n'
            # send data
            connSocket = self.clientInfo['rtspSocket'][0]
            try:
                connSocket.send(reply.encode())
            except Exception as e:
                print(f"Error: Sending RTSP reply(client might has closed)\n{e}")
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")