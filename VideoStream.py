# Replaced VideoStream that supports two input formats:
# 1) "framed" format expected by original server:
#    each frame is stored as 5 ASCII digits (zero-padded) giving the frame length,
#    followed by the frame bytes.
# 2) concatenated MJPEG (common .mjpeg): a sequence of JPEG files concatenated,
#    each starting with 0xFFD8 and ending with 0xFFD9.
#
# The class auto-detects the format at initialization, builds an index for
# concatenated MJPEG for fast nextFrame()/seek(), and preserves the framed
# reader behavior for existing stream files.
#
# Replace the existing VideoStream.py in your server repo with this file,
# then restart the Server. After that you can use your original movie.mjpeg
# (concatenated MJPEG) without converting.

class VideoStream:
    def __init__(self, filename):
        self.filename = filename
        try:
            # Read the whole file once for detection and indexing.
            with open(filename, 'rb') as f:
                self._data = f.read()
        except:
            raise IOError
        self.frameNum = 0
        self.totalFrames = 0
            
        # Detect format:
        # - If file starts with five ASCII digits -> "framed" format (legacy)
        # - Else if file starts with JPEG SOI (0xFFD8) -> concatenated MJPEG
        header = self._data[:5]
        try:
            # If header are ascii digits -> framed format
            int(header.decode('ascii'))
            self._mode = 'framed'
            # For framed mode we keep a cursor position to emulate file.read
            self._cursor = 0
            self._datasize = len(self._data)
        except Exception:
            # Not framed — assume concatenated MJPEG
            self._mode = 'mjpeg'
            # Build list of (start, end) offsets for each JPEG frame
            self._frames = []
            data = self._data
            
            n = len(data)
            i = 0
            while i < n:
                soi = data.find(b'\xff\xd8', i)
                # EOF
                if soi == -1:
                    break
                
                # find EOI for this frame
                eoi = data.find(b'\xff\xd9', soi+2)
                if eoi == -1:
                    # if no EOI, try to find next SOI and use it as boundary
                    next_soi = data.find(b'\xff\xd8', soi+2)
                    
                    if next_soi == -1:
                        # take rest of file
                        self._frames.append((soi, n))
                        i = n
                    else:
                        self._frames.append((soi, next_soi))
                        i = next_soi
                else:
                    self._frames.append((soi, eoi+2))
                    i = eoi+2
                    
            self.totalFrames = len(self._frames)
            # free data? we keep _data to slice frames; it's convenient and simple.
            # If memory is a concern, this can be rewritten to keep file and offsets only.
        # end init

    def nextFrame(self):
        """Get next frame. if EOF, return None"""
        if self._mode == 'framed':
            # Read 5 ASCII bytes for length; if not enough or EOF return None
            if self._cursor + 5 > self._datasize:
                return None
            
            header = self._data[self._cursor:self._cursor+5]
            self._cursor += 5
            try:
                framelength = int(header.decode('ascii'))
            except:
                return None
            
            if self._cursor + framelength > self._datasize:
                return None
            
            frame = self._data[self._cursor:self._cursor + framelength]
            self._cursor += framelength
            self.frameNum += 1
            return frame
        else:
            # mjpeg mode: use precomputed frames list
            if self.frameNum < len(self._frames):
                start, end = self._frames[self.frameNum]
                frame = self._data[start:end]
                self.frameNum += 1
                return frame
            else:
                return None

    def frameNbr(self):
        """Get frame number (how many frames have been returned)."""
        return self.frameNum
    
    def getTotalFrames(self):
        "Get the total frame number of the film"
        return self.totalFrames

    def seek(self, targetFrame):
        """
        Advance to targetFrame (frame count already consumed).
        Example: seek(0) does nothing; seek(5) will make nextFrame() return frame 6.
        """
        if targetFrame <= 0:
            return
        if self._mode == 'framed':
            # reset and read forward to targetFrame
            self._cursor = 0
            self.frameNum = 0
            while self.frameNum < targetFrame:
                # attempt to read a frame; if None break
                header_pos = self._cursor
                if header_pos + 5 > self._datasize:
                    break
                
                header = self._data[self._cursor:self._cursor+5]
                self._cursor += 5
                
                try:
                    framelength = int(header.decode('ascii'))
                except:
                    break
                if self._cursor + framelength > self._datasize:
                    break
                self._cursor += framelength
                self.frameNum += 1
        else:
            # mjpeg mode: clamp target and set frameNum accordingly
            if targetFrame >= len(self._frames):
                # if seeking beyond end, set to last
                self.frameNum = len(self._frames)
            else:
                self.frameNum = targetFrame