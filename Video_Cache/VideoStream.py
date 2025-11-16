class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0
		self.totalFrames = 0
  
		# count the total of the video frame
		while True:
			data = self.file.read(5)
			if not data:
				break
			try:
				framelegth = int(data)
			except:
				print("Unable to Read Frame Length")
				break
			self.file.read(framelegth)
			self.totalFrames += 1
		print(f"Video '{filename}' has {self.totalFrames} frames")
		# Return the file pointer to the beginning
		self.file.seek(0)
		self.frameNum = 0
  
	def nextFrame(self):
		"""Get next frame."""
		data = self.file.read(5) # Get the framelength from the first 5 bits
		if data: 
			framelength = int(data)
							
			# Read the current frame
			data = self.file.read(framelength)
			self.frameNum += 1
		return data
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum
	
	def getTotalFrames(self):
		"""Get total frame number of the film"""
		return self.totalFrames
	