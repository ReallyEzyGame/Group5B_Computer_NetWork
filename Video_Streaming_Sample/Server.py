import sys, socket

from ServerWorker import ServerWorker

class Server:	
	
	def main(self):
		try:
			SERVER_PORT = int(sys.argv[1])
		except:
			print("[Usage: Server.py Server_port]\n")
			sys.exit(1)
		
		rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		rtspSocket.bind(('', SERVER_PORT))
		rtspSocket.listen(5)
		
		print(f"RTSP Server started on port {SERVER_PORT}")
		print("Waiting for client connections...")

		# Receive client info (address,port) through RTSP/TCP session
		while True:
			clientInfo = {}
			clientInfo['rtspSocket'] = rtspSocket.accept()
			print(f"Client connected from {clientInfo['rtspSocket'][1]}")
			ServerWorker(clientInfo).run()		

if __name__ == "__main__":
	(Server()).main()