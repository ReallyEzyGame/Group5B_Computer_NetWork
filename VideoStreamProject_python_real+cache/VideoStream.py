import os

class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0
		
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
		
		chunk = self.file.read(4096)
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
			chunk = self.file.read(4096)
		self.frameNum += 1
		return bytes(data)
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum
	
	