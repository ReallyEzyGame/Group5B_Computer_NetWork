import queue
import time
from tkinter import *
from tkinter import ttk
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os


from RtpPacket import RtpPacket


CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

SLEEP_TIME = 0.04


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
		
  
		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0

		self.frameNbr = 0
		self.totalFrames = 0
		self.fps = 20
		self.frameBuffer = queue.Queue()				# contains frames that is used to cache

		self.playEvent = threading.Event()
  
		self.createWidgets()
		self.connectToServer()
  
	def createWidgets(self):
		"""Build GUI."""
		# Create Setup button
		self.setup = Button(self.master, width=20, padx=3, pady=3)
		self.setup["text"] = "Setup"
		self.setup["command"] = self.setupMovie
		self.setup.grid(row=1, column=0, padx=2, pady=2)
		
		# Create Play button		
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=1, padx=2, pady=2)
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=2, padx=2, pady=2)
		
		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Teardown"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=1, column=3, padx=2, pady=2)
		
		# Create a label to display the movie
		self.label = Label(self.master, height=19)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 

		# Create Time Label
		self.slider_frame = Frame(self.master)
		self.slider_frame.grid(row=2, column=2, columnspan=4, sticky=W+E, padx=5, pady=5)

		self.time_label = Label(self.slider_frame, text="--:-- / --:--")
		self.time_label.pack(side=BOTTOM)
		
		self.timeline_canvas = Canvas(self.slider_frame, height=20, bg='#333333')
		self.timeline_canvas.pack(side=BOTTOM, fill=X, expand=True)
	
  
	def setupMovie(self):
		"""Setup button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
	
 
	def exitClient(self):
		"""Teardown button handler."""
		self.sendRtspRequest(self.TEARDOWN)		
		self.master.destroy() # Close the gui window
		try:
			os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) # Delete the cache image from video
		except FileNotFoundError:
			pass


	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)
			self.playEvent.set()
	
 
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.READY:
			self.playEvent.clear()

			#while not self.frameBuffer.empty():
			#	try:
			#		self.frameBuffer.get_nowait()
			#	except queue.Empty:
			#		break
   
			# Create a new thread to listen for RTP packets
			threading.Thread(target=self.listenRtp).start()
			threading.Thread(target=self.playVideoThread).start()
   
			# self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)
 
 
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
		thumb_radius = 12
		thumb_y_center = canvas_height / 2
  
		self.timeline_canvas.create_oval(watched_x - thumb_radius, thumb_y_center - thumb_radius, watched_x + thumb_radius, thumb_y_center + thumb_radius, fill="#FF0000", outline='#FFFFFF')
  
  
	def listenRtp(self):		
		"""Listen for RTP packets."""
		while True:
			try:
				data = self.rtpSocket.recv(20480)
				if data:
					self.frameBuffer.put(data)
     
			except:
				# Stop listening upon requesting PAUSE or TEARDOWN
				if self.playEvent.is_set(): 
					break
				
				# Upon receiving ACK for TEARDOWN request,
				# close the RTP socket
				if self.teardownAcked == 1:
					self.rtpSocket.shutdown(socket.SHUT_RDWR)
					self.rtpSocket.close()
					break
		
	def playVideoThread(self):
		while True:
			try:
				# Check for PAUSE or TEARDOWN
				if self.playEvent.is_set():
					break
				
				data = self.frameBuffer.get(timeout=0.5)

				if not data:
					continue
				rtpPacket = RtpPacket()
				rtpPacket.decode(data)

				currFrameNbr = rtpPacket.seqNum()
				print("Current Seq Num: " + str(currFrameNbr))

				# Discard the late Packet
				if currFrameNbr > self.frameNbr:
					self.frameNbr = currFrameNbr
					if self.frameNbr % 6 == 0:
						self.updateTimelineCanvas()
						self.updateTimeLabel(currFrameNbr)
	
					self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
				# Handle Jitter
				time.sleep(SLEEP_TIME)
    
			except queue.Empty:
				print("Jitter Buffer is Empty, Waitting for data...")
				# Escape when pause while waiting
				if self.playEvent.is_set():
					break
  
  
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		
		return cachename
	

	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		photo = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image = photo, height=288) 
		self.label.image = photo
	
 	
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			tkinter.messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)
	
 
	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""	
		
		# Setup request
		self.rtspSeq += 1
		request = ""
		if requestCode == self.SETUP and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()
			
			# Write the RTSP request to be sent.
			request += "SETUP " + self.fileName + " " + "RTSP/1.0" + "\n" + "CSeq: " + str(self.rtspSeq) + "\n" + "Transport: RTP/UDP" + "; " + "client_port" + "= " + str(self.rtpPort)
			# Keep track of the sent request.
			self.requestSent = self.SETUP
		
		# Play request
		elif requestCode == self.PLAY and self.state == self.READY:
			
			# Write the RTSP request to be sent.
			request = "PLAY " + self.fileName + " " + "RTSP/1.0" + "\n" + "CSeq: " + str(self.rtspSeq) + "\n" + "Session: " + str(self.sessionId)
			# Keep track of the sent request.
			self.requestSent = self.PLAY
		
		# Pause request
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			
			# Write the RTSP request to be sent.
			request = "PAUSE" + " " + self.fileName + " " + "RTSP/1.0" + "\n" + "CSeq: " + str(self.rtspSeq) + "\n" + "Session: " + str(self.sessionId)
			# Keep track of the sent request.
			self.requestSent = self.PAUSE
			
		# Teardown request
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			# Write the RTSP request to be sent.
			request = "TEARDOWN" + " " + self.fileName + " " + "RTSP/1.0" + "\n" + "CSeq: "  + str(self.rtspSeq) + "\n" + "Session: " + str(self.sessionId)
			# Keep track of the sent request.
			self.requestSent = self.TEARDOWN
   
		else:
			self.rtspSeq -= 1
			return
	
		# Send the RTSP request using rtspSocket.
		self.rtspSocket.send(request.encode())
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
						# Update RTSP state.
						self.state = self.READY

						for line in lines:
							if line.startswith('Video-Length:'):
								self.totalFrames = int(line.split(' ')[1])
								print(f"Server reports {self.totalFrames} frames")
						
						if self.totalFrames > 0:
							pass
     
						# Open RTP port.
						self.openRtpPort() 
					elif self.requestSent == self.PLAY:
						self.state = self.PLAYING
					elif self.requestSent == self.PAUSE:
						self.state = self.READY
						# The play thread exits. A new thread is created on resume.
						# self.playEvent.set()
					elif self.requestSent == self.TEARDOWN:
						self.state = self.INIT
						# Flag the teardownAcked to close the socket.
						self.teardownAcked = 1 
	
 
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		# Create a new datagram socket to receive RTP packets from the server
		# self.rtpSocket = ...
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		# Set the timeout value of the socket to 0.5sec
		# ...
		self.rtpSocket.settimeout(0.5)
		
		try:
			# Bind the socket to the address using the RTP port given by the client user
			self.rtpSocket.bind(('', self.rtpPort))
		except:
			tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)


	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # When the user presses cancel, resume playing.
			self.playMovie()
