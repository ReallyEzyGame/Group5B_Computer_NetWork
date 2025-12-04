# 04/12/2025, Adding time bar, chache bar, fixing recvRtsp, writeFrame, updateMovie... for cache
# Adding more attribute to the Client class for cache

from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
import time

from RtpPacket import RtpPacket
import queue
CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"
_TIME_SLEEP_ = 0.05

class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT

	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
 
 
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)

		# Connection params
		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename

		# RTSP state
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0

		# Playback state
		self.frameNbr = 0
		self.requestStartFrame = 0
		self.totalFrames = 0
		self.fps = 20
		self.frameBuffer = queue.Queue()				# contains frames that is used to cache
		# Fragment reassembly buffer: frameId -> list of (pktSeq, chunk)
		self.fragment_buffer = {}

		# sockets
		self.rtspSocket = None
		self.rtpSocket = None

		# events
		self.playEvent = None

		# desired display area initial size (will adapt)
		self.display_width = 960
		self.display_height = 540

		# Keep reference to current displayed PhotoImage to avoid GC
		self._photo_image = None

		# Create UI and connect
		self.createWidgets()
		self.connectToServer()

	# ---------------- UI ----------------
	def createWidgets(self):
		# Configure grid so video area expands
		for c in range(4):
			self.master.grid_columnconfigure(c, weight=1)
		self.master.grid_rowconfigure(0, weight=1)

		# Container frame for video with fixed minsize
		self.video_frame = Frame(self.master, bg="black")
		self.video_frame.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5)
		self.video_frame.grid_propagate(False)
		self.video_frame.update_idletasks()
		self.video_frame.config(width=self.display_width, height=self.display_height)

		# Canvas for image rendering
		self.canvas = Canvas(self.video_frame, bg="black", highlightthickness=0)
		self.canvas.place(relx=0, rely=0, relwidth=1, relheight=1)

		# Controls
		self.setup = Button(self.master, width=20, padx=3, pady=3, text="Setup", command=self.setupMovie)
		self.setup.grid(row=1, column=0, padx=2, pady=2, sticky='n')

		# Play button
		self.start = Button(self.master, width=20, padx=3, pady=3, text="Play", command=self.playMovie)
		self.start.grid(row=1, column=1, padx=2, pady=2, sticky='n')

		# Pause button
		self.pause = Button(self.master, width=20, padx=3, pady=3, text="Pause", command=self.pauseMovie)
		self.pause.grid(row=1, column=2, padx=2, pady=2, sticky='n')
		
		# Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3, text="Teardown", command=self.exitClient)
		self.teardown.grid(row=1, column=3, padx=2, pady=2, sticky='n')

		# Resolution radio buttons
		self.resolutionVar = IntVar()
		self.resolutionVar.set(0)
		self.high = Radiobutton(self.master, width=10, padx=3, pady=3, variable=self.resolutionVar, value=1, text="1080p", command=self.switchToHigh)
		self.high.grid(row=2, column=0, padx=2, pady=2, sticky='n')
		self.default = Radiobutton(self.master, width=10, padx=3, pady=3, variable=self.resolutionVar, value=0, text="720p", command=self.switchToDefault)
		self.default.grid(row=2, column=1, padx=2, pady=2, sticky='n')

		# Create Time Label
		self.slider_frame = Frame(self.master)
		self.slider_frame.grid(row=2, column=2, columnspan=4, sticky=W+E, padx=5, pady=5)

		self.time_label = Label(self.slider_frame, text="--:-- / --:--")
		self.time_label.pack(side=BOTTOM)
		
		self.timeline_canvas = Canvas(self.slider_frame, height=10, bg='#333333')
		self.timeline_canvas.pack(side=BOTTOM, fill=X, expand=True)
  
		# Bind resize so we can adapt displayed image if user resizes window
		self.master.bind("<Configure>", self._on_window_resize)

	def _on_window_resize(self, event):
		try:
			w = self.video_frame.winfo_width()
			h = self.video_frame.winfo_height()
			if w > 20 and h > 20:
				self.display_width = w
				self.display_height = h
		except:
			pass

	# ---------------- Networking ----------------
	def connectToServer(self):
		# Close existing socket if any
		try:
			if self.rtspSocket:
				try:
					self.rtspSocket.shutdown(socket.SHUT_RDWR)
				except:
					pass
				try:
					self.rtspSocket.close()
				except:
					pass
		except:
			pass

		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
			print("Connected to RTSP server", self.serverAddr, self.serverPort)
		except Exception as e:
			tkinter.messagebox.showwarning('Connection Failed', f"Connection to '{self.serverAddr}' failed: {e}")

	# ---------------- Controls ----------------
	def setupMovie(self):
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)

	def exitClient(self):
		# send TEARDOWN then close UI
		if self.state != self.INIT:
			try:
				self.sendRtspRequest(self.TEARDOWN)
			except:
				pass

		# stop play listener
		if hasattr(self, 'playEvent') and self.playEvent:
			try:
				self.playEvent.set()
			except:
				pass

		# close RTP socket
		try:
			if self.rtpSocket:
				self.rtpSocket.close()
		except:
			pass

		# close RTSP socket
		try:
			if self.rtspSocket:
				self.rtspSocket.close()
		except:
			pass

		try:
			self.master.destroy()
		except:
			pass
		# remove cache file if exists
		try:
			os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
		except:
			pass

	def updateTimeLabel(self, currentFrame):
		"""Update the Time Label"""
		if self.totalFrames == 0:
			return
 
		current_sec = currentFrame / self.fps
		total_sec = self.totalFrames / self.fps

		current_time_str = "{:02}:{:02}".format(int(current_sec // 60), int(current_sec % 60))
		total_time_str = "{:02}:{:02}".format(int(current_sec // 60), int(total_sec % 60))

		self.time_label.config(text=f"{current_time_str} / {total_time_str}")
  
	def updateTimelineCanvas(self):
		"""ReDraw the canvas time bar(cache, watched)"""
		canvas_width = self.timeline_canvas.winfo_width()
		canvas_height = self.timeline_canvas.winfo_height()
  
		# Stop if Canvas has not been draw yet
		if canvas_width <= 1 or canvas_height <= 1 or self.totalFrames == 0:
			return
		currentFrame = self.frameNbr

		cachedFrames = min(self.totalFrames, currentFrame + self.frameBuffer.qsize())
  
		# Calculate Pixel position
		watched_x = (currentFrame / self.totalFrames) * canvas_width
		cached_x = (cachedFrames / self.totalFrames) * canvas_width
  
		# Draw layer by layer
		bar_y_start = 0
		bar_y_end = 100
		# Bar's  Theme
		self.timeline_canvas.create_rectangle(0,  bar_y_start, canvas_width, bar_y_end, fill="#555555", width=0)
		# Cache Bar
		self.timeline_canvas.create_rectangle(0, bar_y_start, cached_x, bar_y_end, fill="#AAAAAA", width=0)
		# Watched Bar
		self.timeline_canvas.create_rectangle(0,  bar_y_start, watched_x, bar_y_end, fill="#FF0000", width=0)
		# Thumb Button
		thumb_radius = 8
		thumb_y_center = canvas_height / 2
  
		self.timeline_canvas.create_oval(watched_x - thumb_radius, thumb_y_center - thumb_radius, watched_x + thumb_radius, thumb_y_center + thumb_radius, fill="#FFFFFF", outline="#000000")
	def pauseMovie(self):
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)

	def playMovie(self):
		if self.state == self.READY:
			# prepare playEvent and start RTP listener thread
			self.playEvent = threading.Event()
			self.playEvent.clear()

			threading.Thread(target=self.listenRtp, daemon=True).start()
			threading.Thread(target=self.playVideoThread).start()

			self.sendRtspRequest(self.PLAY)

	def playVideoThread(self):
		while True:
			try:
				data = self.frameBuffer.get()
				if data:
					rtpPacket = RtpPacket()
					try:
						rtpPacket.decode(data)
					except Exception as e:
						print("Failed to decode RTP packet:", e)
						continue

					pktSeq = rtpPacket.seqNum()
					payload = rtpPacket.getPayload()

					# If using fragmentation header: 4 bytes frameId + 1 byte last_flag
					if len(payload) >= 5:
						frameId = int.from_bytes(payload[:4], 'big')
						last_flag = payload[4]
						chunk = payload[5:]
						buf = self.fragment_buffer.setdefault(frameId, [])
      
						buf.append((pktSeq, chunk))
      
						if last_flag == 1:
							buf.sort(key=lambda x: x[0])
							frame_bytes = b''.join([c for _, c in buf])
							try:
								del self.fragment_buffer[frameId]
							except:
								pass
							# display only newer frames
							if frameId > self.frameNbr:
								self.frameNbr = frameId
								self.updateMovie(frame_bytes)
        
								if self.frameNbr % 20 == 0:
									self.updateTimeLabel(self.frameNbr)
									self.updateTimelineCanvas()
					else:
						# legacy: treat entire payload as JPEG
						currFrameNbr = rtpPacket.seqNum()
						if currFrameNbr > self.frameNbr:
							self.frameNbr = currFrameNbr
							self.updateMovie(payload)
       
							if self.frameNbr % 20 == 0:
								self.updateTimeLabel(self.frameNbr)
								self.updateTimelineCanvas()
			except socket.timeout:
				continue
			except OSError:
				break
			except Exception as e:
				# stop if playEvent set
				if hasattr(self, 'playEvent') and self.playEvent and self.playEvent.is_set():
					break
				# if teardown acked, close socket
				if self.teardownAcked == 1:
					try:
						self.rtpSocket.shutdown(socket.SHUT_RDWR)
					except:
						pass
					try:
						self.rtpSocket.close()
					except:
						pass
					break
				print("listenRtp exception:", e)
				traceback.print_exc()
				break
		# Wait for a current time
		time.sleep(_TIME_SLEEP_)
	# ---------------- RTP listening & assembly ----------------
	def listenRtp(self):
		while True:
			try:
				data = self.rtpSocket.recv(65535)

				if data:
					self.frameBuffer.put(data)

			except socket.timeout:
				continue
			except OSError:
				break
			except Exception as e:
				# stop if playEvent set
				if hasattr(self, 'playEvent') and self.playEvent and self.playEvent.is_set():
					break
				# if teardown acked, close socket
				if self.teardownAcked == 1:
					try:
						self.rtpSocket.shutdown(socket.SHUT_RDWR)
					except:
						pass
					try:
						self.rtpSocket.close()
					except:
						pass
					break
				print("listenRtp exception:", e)
				traceback.print_exc()
				break

	# ---------------- image handling ----------------
	def writeFrame(self, data):
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		with open(cachename, "wb") as file:
			file.write(data)
   
		return cachename

	def updateMovie(self, imageOrBytes):
		# Ensure GUI update runs on main thread
		self.master.after(0, lambda: self._update_image(imageOrBytes))

	def _update_image(self, imageOrBytes):
		try:
			# Load image (from bytes or path)
			if isinstance(imageOrBytes, (bytes, bytearray)):
				cachename = self.writeFrame(imageOrBytes)
				img = Image.open(cachename)
			else:
				img = Image.open(imageOrBytes)

			cw = max(1, self.display_width)
			ch = max(1, self.display_height)
			orig_w, orig_h = img.size

			# Calculate new size keeping aspect ratio
			ratio = min(cw / orig_w, ch / orig_h)
			new_w = max(1, int(orig_w * ratio))
			new_h = max(1, int(orig_h * ratio))

			resized = img.resize((new_w, new_h), Image.LANCZOS)

			photo = ImageTk.PhotoImage(resized)
			self._photo_image = photo  # keep reference

			# clear previous image
			self.canvas.delete("VIDEO_IMG")
   
			x = (cw - new_w) // 2
			y = (ch - new_h) // 2
			self.canvas.create_image(x, y, anchor='nw', image=photo, tags="VIDEO_IMG")
			self.canvas.update_idletasks()
   
		except Exception as e:
			print("updateMovie error:", e)
			traceback.print_exc()

	# ---------------- RTSP request/response ----------------
	def sendRtspRequest(self, requestCode):
		# increment seq
		self.rtspSeq += 1
		# SETUP
		if requestCode == self.SETUP and self.state == self.INIT:
			# start receiver thread for RTSP replies
			threading.Thread(target=self.recvRtspReply, daemon=True).start()
			request = (
				f"SETUP {self.fileName} RTSP/1.0\r\n"
				f"CSeq: {self.rtspSeq}\r\n"
				f"Transport: RTP/UDP; client_port={self.rtpPort}\r\n"
			)
			if getattr(self, 'requestStartFrame', 0):
				request += f"Start-Frame: {self.requestStartFrame}\r\n"
				self.requestStartFrame = 0
			request += "\r\n"
			self.requestSent = self.SETUP

		# PLAY
		elif requestCode == self.PLAY and self.state == self.READY:
			request = (
				f"PLAY {self.fileName} RTSP/1.0\r\n"
				f"CSeq: {self.rtspSeq}\r\n"
				f"Session: {self.sessionId}\r\n\r\n"
			)
			self.requestSent = self.PLAY

		# PAUSE
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			request = (
				f"PAUSE {self.fileName} RTSP/1.0\r\n"
				f"CSeq: {self.rtspSeq}\r\n"
				f"Session: {self.sessionId}\r\n\r\n"
			)
			self.requestSent = self.PAUSE

		# TEARDOWN
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			request = (
				f"TEARDOWN {self.fileName} RTSP/1.0\r\n"
				f"CSeq: {self.rtspSeq}\r\n"
				f"Session: {self.sessionId}\r\n\r\n"
			)
			self.requestSent = self.TEARDOWN
		else:
			return

		try:
			self.rtspSocket.sendall(request.encode("utf-8"))
			print('\nData sent:\n' + request)
		except BrokenPipeError as e:
			# If broken pipe while sending SETUP, attempt reconnect-and-resend once
			print("BrokenPipe while sending RTSP request:", e)
   
			if requestCode == self.SETUP:
				try:
					self.connectToServer()
					self.rtspSocket.sendall(request.encode("utf-8"))
					print("Reconnected and resent SETUP")
				except Exception as e2:
					print("Failed to resend SETUP after reconnect:", e2)
			else:
				print("Cannot resend non-SETUP request")
		except Exception as e:
			print("Failed to send RTSP request:", e)
			traceback.print_exc()

	def recvRtspReply(self):
		while True:
			try:
				reply = self.rtspSocket.recv(4096)
			except OSError:
				break
			except Exception:
				break

			if reply:
				try:
					self.parseRtspReply(reply.decode("utf-8"))
				except Exception as e:
					print("Failed to parse RTSP reply:", e)
					traceback.print_exc()

			if self.requestSent == self.TEARDOWN and self.teardownAcked == 1:
				try:
					self.rtspSocket.shutdown(socket.SHUT_RDWR)
				except:
					pass
   
				try:
					self.rtspSocket.close()
				except:
					pass
				break

	def parseRtspReply(self, data):
		lines = data.splitlines()
		print("RTSP reply received:\n", data)

		# status
		status_code = None
  
		if len(lines) >= 1:
			parts = lines[0].split()
			if len(parts) >= 2:
				try:
					status_code = int(parts[1])
				except:
					status_code = None
		# find CSeq and Session
		seqNum = None
		session = None
  
		for line in lines[1:]:
			if line.strip().lower().startswith("cseq"):
				try:
					seqNum = int(line.split(":", 1)[1].strip())
				except:
					seqNum = None
			elif line.strip().lower().startswith("session"):
				val = line.split(":", 1)[1].strip()
				val = val.split(";")[0].strip()
				try:
					session = int(val)
				except:
					session = None


		if seqNum is None:
			print("No CSeq in RTSP reply, ignoring")
			return

		if seqNum == self.rtspSeq:
			if self.sessionId == 0 and session is not None:
				self.sessionId = session

			if session is None or self.sessionId == session:
				if status_code == 200:
					if self.requestSent == self.SETUP:
						# get total frame
						if (len(lines) >= 5):
							self.totalFrames = int(lines[3].split(" ", 1)[1].strip())
       
						self.state = self.READY
						# open RTP port for incoming packets
						self.openRtpPort()
					elif self.requestSent == self.PLAY:
						self.state = self.PLAYING
					elif self.requestSent == self.PAUSE:
						self.state = self.READY
						if hasattr(self, 'playEvent') and self.playEvent:
							self.playEvent.set()
					elif self.requestSent == self.TEARDOWN:
						self.state = self.INIT
						self.teardownAcked = 1
				else:
					print("RTSP server returned error code:", status_code)

	def openRtpPort(self):
		# close previous rtp socket if any
		try:
			if self.rtpSocket:
				try:
					self.rtpSocket.close()
				except:
					pass
		except:
			pass

		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.rtpSocket.settimeout(0.5)
		try:
			self.rtpSocket.bind(("", self.rtpPort))
			print("Opened RTP port", self.rtpPort)
		except Exception as e:
			tkinter.messagebox.showwarning('Unable to Bind', f'Unable to bind PORT={self.rtpPort}: {e}')
	# exit option
	def handler(self):
		self.pauseMovie()
		if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else:
			self.playMovie()

	# ---------------- resolution switching logic (safe-method) ----------------
	def _switch_resolution(self, new_filename):
		"""
		Run in background thread:
		- request TEARDOWN, wait for ack (short timeout)
		- stop RTP listener and close RTP socket
		- close and reconnect RTSP socket
		- set new filename and Start-Frame
		- send SETUP for new file
		"""
		current_frame = self.frameNbr

		# If currently playing, ask teardown
		if self.state != self.INIT:
			try:
				self.sendRtspRequest(self.TEARDOWN)
			except Exception as e:
				print("Error sending TEARDOWN:", e)

			# wait for ack up to 2s
			deadline = time.time() + 2.0
			while time.time() < deadline and self.teardownAcked != 1:
				time.sleep(0.05)

		# stop RTP listener
		if hasattr(self, 'playEvent') and self.playEvent:
			try:
				self.playEvent.set()
			except:
				pass

		# close rtp socket
		try:
			if self.rtpSocket:
				try:
					self.rtpSocket.close()
				except:
					pass
				self.rtpSocket = None
		except:
			pass

		# reset fragment buffer
		self.fragment_buffer.clear()
		# clear the cache buffer
		self.frameBuffer = queue.Queue()
		# close and reconnect RTSP socket
		try:
			if self.rtspSocket:
				try:
					self.rtspSocket.shutdown(socket.SHUT_RDWR)
				except:
					pass
				try:
					self.rtspSocket.close()
				except:
					pass
		except:
			pass

		# reconnect
		self.connectToServer()

		# set up new file and start frame
		self.requestStartFrame = current_frame + 1
		self.fileName = new_filename

		# reset RTSP state for new session
		self.state = self.INIT
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0

		# send SETUP for new file
		try:
			self.sendRtspRequest(self.SETUP)
		except Exception as e:
			print("Error sending SETUP after switch:", e)

	def switchToHigh(self):
		print("Switching to high resolution...")
		if "_high" in self.fileName:
			print("Already high resolution")
			return
 
		dot = self.fileName.rfind(".")
		new_file = self.fileName[:dot] + "_high" + self.fileName[dot:]
		# run background worker
		threading.Thread(target=self._switch_resolution, args=(new_file,), daemon=True).start()
		# attempt play after a small delay (SETUP reply should open RTP port and set READY)
		self.master.after(500, self.playMovie)

	def switchToDefault(self):
		print("Switching to default resolution...")
		if "_high" not in self.fileName:
			print("Already default resolution")
			return

		new_file = self.fileName.replace("_high", "")
		threading.Thread(target=self._switch_resolution, args=(new_file,), daemon=True).start()
		self.master.after(500, self.playMovie)

