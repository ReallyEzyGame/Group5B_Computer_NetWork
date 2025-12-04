class CacheBuffer:
    def __init__(self, capacity):
        self.capacity = capacity
        self.buffer = [None] * capacity
        self.readHandle = 0
        self.writeHandle = 0
        self.lock = True
    
    def read(self):
        if self.lock:
            return None

        result = self.buffer[self.readHandle]
        self.buffer[self.readHandle] = None
        
        self.readHandle = (self.readHandle + 1) % self.capacity
        
        if (self.readHandle == self.writeHandle):
            self.lock = True
        
        return result
    
    def write(self, data):
        if self.writeHandle == self.readHandle and not self.lock:
            return False
        
        self.buffer[self.writeHandle] = data
        self.writeHandle = (self.writeHandle + 1) % self.capacity

        if self.writeHandle == self.readHandle:
            self.lock = False

        return True
    
    def isLocked(self):
        return self.lock

    def unlock(self):
        self.lock = False

    def lock(self):
        self.lock = True