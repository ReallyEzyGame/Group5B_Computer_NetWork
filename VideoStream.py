import os

class VideoStream:
	CHUNK_SIZE = 4 * 1024 * 1024

	def __init__(self, filename):
		self.filename = filename
		self.frameNum = 0
		self.framePos = []

		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		
		chunk = self.file.read(self.CHUNK_SIZE)
		border = b''
		fileOffset = 0
  
		while chunk:
			start = 0
			buf = border + chunk
   
			while True:
				pos = buf.find(b'\xFF\xD8', start)
				if pos == -1:
					break

				self.framePos.append(fileOffset + pos - len(border))
				start = pos + 2

			border = chunk[-1:]
			fileOffset += len(chunk)
			chunk = self.file.read(self.CHUNK_SIZE)
		
		self.file.seek(0, os.SEEK_SET)
		
	def nextFrame(self):
		"""Get next frame."""
		data = bytearray()

		prev = None
		while True:
			byte = self.file.read(1)
   
			if not byte:
				break
			if prev == b'\xFF' and byte == b'\xD8':
				data.extend(b"\xFF\xD8")
				break
			prev = byte
		
		chunk = self.file.read(self.CHUNK_SIZE)
		prev = None
  
		while chunk:
			break_f = False
   
			for i in range(len(chunk)):
				if prev == 0xFF and chunk[i] == 0xD9:
					break_f = True
					data.extend(chunk[:i + 1])
					self.file.seek(-(len(chunk) - 1 - i), os.SEEK_CUR)
					break
   
				prev = chunk[i]
			if break_f:
				break
  
			data.extend(chunk)
			chunk = self.file.read(self.CHUNK_SIZE)
   
		self.frameNum += 1
		return bytes(data)
	
	def seek(self, target):
		if target >= len(self.framePos):
			self.file.seek(0, os.SEEK_END)
			self.frameNum = len(self.framePos)
			return
 
		self.file.seek(self.framePos[target], os.SEEK_SET)
		self.frameNum = target
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum
	
	def getTotalFrames(self):
		return len(self.framePos)