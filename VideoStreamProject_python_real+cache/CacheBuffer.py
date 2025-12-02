class CacheBuffer:
    def __init__(self, capacity):
        self.capacity = capacity
        self.buffer = [None] * capacity
        self.readHandle = 0
        self.writeHandle = 0
        self.lock = False
    
    def read(self):
        if self.lock:
            return None

        result = self.buffer[self.readHandle]
        self.buffer[self.readHandle] = None
        
        if (self.readHandle != self.writeHandle):
            self.readHandle = (self.readHandle + 1) % self.capacity
        else:
            self.lock = True
        
        return result
    
    def write(self, data):
        if self.writeHandle == self.readHandle:
            self.lock = False
            return False
        
        self.buffer[self.writeHandle] = data
        self.writeHandle = (self.writeHandle + 1) % self.capacity

        return True
