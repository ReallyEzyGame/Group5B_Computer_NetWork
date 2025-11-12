import socket
import sys

def test_server_connection(host, port):
    """Test if the server is reachable."""
    print(f"Testing connection to {host}:{port}...")
    
    try:
        # Create socket
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.settimeout(5)
        
        # Try to connect
        test_socket.connect((host, int(port)))
        print("✓ Successfully connected to server!")
        print("✓ Server is running and accepting connections")
        
        test_socket.close()
        return True
        
    except socket.timeout:
        print("✗ Connection timeout - server might not be running")
        return False
    except ConnectionRefusedError:
        print("✗ Connection refused - server is not running on this port")
        return False
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_connection.py <host> <port>")
        print("Example: python test_connection.py localhost 8554")
        sys.exit(1)
    
    host = sys.argv[1]
    port = sys.argv[2]
    
    print("=" * 50)
    print("RTSP Server Connection Test")
    print("=" * 50)
    
    if test_server_connection(host, port):
        print("\n✓ Server is ready! You can now run the client.")
    else:
        print("\n✗ Cannot connect to server!")
        print("\nTroubleshooting steps:")
        print("1. Make sure the server is running:")
        print("   python Server.py 8554")
        print("2. Check if the port is correct")
        print("3. Check if firewall is blocking the connection")
        print("4. Try using '127.0.0.1' instead of 'localhost'")