from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os, io

from RtpPacket import RtpPacket
from CacheBuffer import CacheBuffer

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
	
	# Initiation..
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets()
		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0
		self.connectToServer()
		self.frameNbr = 0

		self.currentFrame = 0
		self.totalFrames = 0
		self.fps = 20
		self.buffer = CacheBuffer(1 * self.fps) # cache 1 seconds

		self.playEvent = threading.Event()
		self.listenEvent = threading.Event()
		
	def createWidgets(self):
		"""Build GUI."""
		# Create Setup button
		self.setup = Button(self.master, width=20, padx=3, pady=3)
		self.setup["text"] = "Setup"
		self.setup["command"] = self.setupMovie
		self.setup.grid(row=2, column=0, padx=2, pady=2)
		
		# Create Play button		
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=2, column=1, padx=2, pady=2)
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=2, column=2, padx=2, pady=2)
		
		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Teardown"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=2, column=3, padx=2, pady=2)
		
		# Create a label to display the movie
		self.label = Label(self.master, height=19)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5)

		timeContainer = Frame(self.master)
		timeContainer.grid(row=1, column=0, columnspan=4, sticky=W+E+N+S)

		timeContainer.grid_columnconfigure(1, weight=2)

		self.time = Label(timeContainer, text="--:-- / --:--")
		self.time.grid(row=0, column=0, sticky=W+E+N+S, padx=5, pady=5)

		timelineContainer = Frame(timeContainer, bg="#E0E0E0")
		timelineContainer.grid(row=0, column=1, sticky=W+E+N+S, padx=5, pady=5)

		self.bufferline = Canvas(timelineContainer, bg="#C2C2C2", highlightthickness=0)
		self.bufferline.place(relx=0, rely=0, relwidth=0.0)
		self.timeline = Canvas(timelineContainer, bg="#F45B69", highlightthickness=0)
		self.timeline.place(relx=0, rely=0, relwidth=0.0)

	def setupMovie(self):
		"""Setup button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
	
	def exitClient(self):
		"""Teardown button handler."""
		self.sendRtspRequest(self.TEARDOWN)
		self.stopListen()
		self.stopDisplay()
		self.master.destroy() # Close the gui window
		# os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) # Delete the cache image from video

	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.state = self.READY
			self.stopDisplay()
	
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.READY:
			print("yak")
			# Create a new thread to listen for RTP packets
			self.startListen()
			self.startDisplay()
			self.sendRtspRequest(self.PLAY)
	
	def startListen(self):
		if self.listenEvent.is_set():
			self.listenEvent.clear()
		threading.Thread(target=self.listenRtp).start()

	def startDisplay(self):
		if self.playEvent.is_set():
			self.playEvent.clear()
		threading.Thread(target=self.displayFrame).start()

	def stopListen(self):
		self.listenEvent.set()

	def stopDisplay(self):
		self.playEvent.set()
	
	def listenRtp(self):
		print("yes")
		"""Listen for RTP packets."""
		while True:
			try:
				# Stop listening upon requesting PAUSE or TEARDOWN
				if self.listenEvent.is_set():
					break

				data = self.rtpSocket.recv(20480)
				if data:
					rtpPacket = RtpPacket()
					rtpPacket.decode(data)
					
					currFrameNbr = rtpPacket.seqNum()
					print("Current Seq Num: " + str(currFrameNbr))

					if not self.buffer.write(rtpPacket):
						self.stopListen()
						self.sendRtspRequest(self.PAUSE)
					elif currFrameNbr > self.frameNbr:
						self.frameNbr = currFrameNbr			
						buffer = self.frameNbr / self.totalFrames
						self.bufferline.place_configure(relwidth=buffer)

			except OSError:
				break
			except:
				# Upon receiving ACK for TEARDOWN request,
				# close the RTP socket
				if self.teardownAcked == 1:
					self.rtpSocket.shutdown(socket.SHUT_RDWR)
					self.rtpSocket.close()
					break
	
	def displayFrame(self):
		while True:
			try:
				if self.playEvent.is_set():
					break

				data = self.buffer.read()
				if data:
					if self.listenEvent.is_set():
						self.startListen()
						self.sendRtspRequest(self.PLAY)
					print(data.seqNum())
					if data.seqNum() > self.currentFrame: # Discard the late packet
						self.playEvent.wait(1/self.fps)
						self.currentFrame = data.seqNum()
						self.updateMovie(data.getPayload())
			except:
				if self.teardownAcked == 1:
					self.rtpSocket.shutdown(socket.SHUT_RDWR)
					self.rtpSocket.close()
					break
					
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		
		return cachename
	
	def updateMovie(self, imageData):
		"""Update the image file as video frame in the GUI."""
		photo = ImageTk.PhotoImage(Image.open(io.BytesIO(imageData)))
		self.label.configure(image = photo, height=288) 
		self.label.image = photo

		if self.totalFrames == 0:
			return

		totalSec = int(self.totalFrames / self.fps)

		time = self.currentFrame / self.totalFrames
		self.time.config(text="{:02}:{:02} / {:02}:{:02}".format(
			int(time * totalSec // 60), int(time * totalSec) % 60,
			int(totalSec // 60), totalSec % 60
		))

		self.timeline.place_configure(relwidth=time)
		
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			tkinter.messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)
	
	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""	
		#-------------
		# TO COMPLETE
		#-------------

		self.rtspSeq += 1
		
		# Setup request
		if requestCode == self.SETUP and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()
			# Update RTSP sequence number.
			# ...
			
			# Write the RTSP request to be sent.
			request = f"SETUP { self.fileName } RTSP/1.0 \r\nCSeq: { self.rtspSeq } \r\nTransport: RTP/UDP; client_port= { self.rtpPort }"
			
			# Keep track of the sent request.
			self.requestSent = self.SETUP
		
		# Play request
		elif requestCode == self.PLAY and self.state == self.READY:
			# Update RTSP sequence number.
			# ...
			
			# Write the RTSP request to be sent.
			request = f"PLAY { self.fileName } RTSP/1.0 \r\nCSeq: { self.rtspSeq } \r\nSession: { self.sessionId }"
			
			# Keep track of the sent request.
			self.requestSent = self.PLAY
		
		# Pause request
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			# Update RTSP sequence number.
			# ...
			
			# Write the RTSP request to be sent.
			request = f"PAUSE { self.fileName } RTSP/1.0 \r\nCSeq: { self.rtspSeq } \r\nSession: { self.sessionId }"
			
			# Keep track of the sent request.
			self.requestSent = self.PAUSE
			
		# Teardown request
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			# Update RTSP sequence number.
			# ...
			
			# Write the RTSP request to be sent.
			request = f"TEARDOWN { self.fileName } RTSP/1.0 \r\nCSeq: { self.rtspSeq } \r\nSession: { self.sessionId }"
			
			# Keep track of the sent request.
			self.requestSent = self.TEARDOWN
		else:
			return
		
		# Send the RTSP request using rtspSocket.
		self.rtspSocket.sendall(request.encode("utf-8"))
		print('\nData sent:\n' + request)
	
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			reply = self.rtspSocket.recv(1024)
			
			if reply:
				self.parseRtspReply(reply.decode("utf-8"))
			
			# Close the RTSP socket upon requesting Teardown
			if self.requestSent == self.TEARDOWN:
				self.rtspSocket.shutdown(socket.SHUT_RDWR)
				self.rtspSocket.close()
				break
	
	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		lines = data.split('\n')
		print(data)
		seqNum = int(lines[1].split(' ')[1])
		
		# Process only if the server reply's sequence number is the same as the request's
		if seqNum == self.rtspSeq:
			session = int(lines[2].split(' ')[1])
			# New RTSP session ID
			if self.sessionId == 0:
				self.sessionId = session
			
			# Process only if the session ID is the same
			if self.sessionId == session:
				if int(lines[0].split(' ')[1]) == 200:
					if self.requestSent == self.SETUP:
						#-------------
						# TO COMPLETE
						#-------------
						# Update RTSP state.
						self.state = self.READY

						self.totalFrames = int(lines[3].split(' ')[1])
						
						# Open RTP port.
						self.openRtpPort()
					elif self.requestSent == self.PLAY:
						self.state = self.PLAYING
					elif self.requestSent == self.PAUSE:
						self.state = self.READY
						
						# The play thread exits. A new thread is created on resume.
						self.stopListen()
					elif self.requestSent == self.TEARDOWN:
						self.state = self.INIT
						
						# Flag the teardownAcked to close the socket.
						self.teardownAcked = 1 
	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		#-------------
		# TO COMPLETE
		#-------------
		# Create a new datagram socket to receive RTP packets from the server
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		
		# Set the timeout value of the socket to 0.5sec
		self.rtpSocket.settimeout(0.5)
		
		try:
			# Bind the socket to the address using the RTP port given by the client user
			self.rtpSocket.bind(("", self.rtpPort))
		except:
			tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)

	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # When the user presses cancel, resume playing.
			self.playMovie()
