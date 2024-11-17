import socket
import threading
import protocol
import os
import select
import sys
from queue import Queue 

if (len(sys.argv) != 2):
    print("Expected 2 arguments, got", len(sys.argv))
    exit()


packetManager = protocol.PacketManager.getInstance()
nameToSocket = {}
socketToName = {}
toLog = Queue()

#Main thread which listens for new clients joining
def startServer():
    #Open server
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.bind(('', int(sys.argv[1])))
    serversocket.listen(5)

    while True:
        #Recieve new client and start a thread
        read, write, error = select.select([serversocket], [], [], 0.1)
        if (len(read) != 0):
            (clientsocket, address) = serversocket.accept()
            print("Client joined with address " + str(address[0]) + " on port " + str(address[1]))
            toLog.put("Client joined with address " + str(address[0]) + " on port " + str(address[1]))
            thread = threading.Thread(target=clientThread, args=(clientsocket, socketToName, nameToSocket,), daemon=True)   #new daemon thread
            thread.start()
        #Log any pending messages
        if (not toLog.empty()):
            with open("./server.log", "a") as logFile:
                while not toLog.empty():
                    x = toLog.get()
                    logFile.write(x + "\n")
            



#Thread which listens for packets from client and sends appropriate response
def clientThread(clientsocket: socket.socket, socketToName, nameToSocket):
    packetManager.send(clientsocket, protocol.Message64bytePacket().setMessage("Welcome, you have succesfully joined the server").setName("Server"))
    packetManager.send(clientsocket, protocol.EndStreamPacket().setPacketType(protocol.Message64bytePacket))

    messageStream = ""
    messageReciever = ""

    try:
        while True:
            #Wait to recieve a packet, then check what type of packet it is
            packet = packetManager.recieve(clientsocket)

            #Sent by a client when they set their name
            if (type(packet) == protocol.SetName16BytePacket):
                name = packet.getName()
                messagePacket = protocol.Message64bytePacket()

                #Check if they're joining for the first time
                if (name not in nameToSocket.keys()):
                    toLog.put(str(clientsocket.getpeername()) + " set name to " + name)
                    messagePacket.setMessage(name + " has joined").setName("Server")
                else:
                    toLog.put(oldName + " set name to " + name)
                    messagePacket.setMessage(oldName + " has renamed to " + name).setName("Server")

                    oldName = socketToName[clientsocket]
                    nameToSocket.pop(oldName)

                #Map client's socket with their new name
                socketToName[clientsocket] = name
                nameToSocket[name] = clientsocket

                #Notify all clients of the update
                for socket in socketToName.keys():
                    packetManager.send(socket, messagePacket)
                    packetManager.send(socket, protocol.EndStreamPacket().setPacketType(protocol.Message64bytePacket))
        
            #This is a 64-chunk of a message sent by a client 
            elif (type(packet) == protocol.Message64bytePacket):
                #Add the chunks together
                messageStream += packet.getMessage()
                messageReciever = packet.getName()

            #Sent by client when they have sent all message chunks for a given message
            elif (type(packet) == protocol.EndStreamPacket):
                #Checks to make sure sure if the packet is ending the correct chunk stream
                if (packet.getPacketType() == protocol.Message64bytePacket):

                    #Updates name of packet to represent who sent the packet rather than who is meant to recieve the packet
                    sender = socketToName[clientsocket]

                    #Break message back into chunks to be passed on again
                    packets = protocol.Message64bytePacket.toPackets(messageStream)
                    for messagePacket in packets:
                        messagePacket.setName(sender)
                    
                    #No recieve specified, so the message is a broadcast
                    if (messageReciever == ""):
                        print(sender + ": " + messageStream)
                        toLog.put(sender + ": " + messageStream)
                        for socket in socketToName.keys():
                            for messagePacket in packets:
                                packetManager.send(socket, messagePacket)
                            packetManager.send(socket, protocol.EndStreamPacket().setPacketType(protocol.Message64bytePacket))
                    else:
                        #Message is a unicast
                        if messageReciever in nameToSocket.keys():
                            print(sender + " to " + messageReciever + ": " + messageStream)
                            toLog.put(sender + " to " + messageReciever + ": " + messageStream)
                            socket = nameToSocket[messageReciever]
                            for messagePacket in packets:
                                packetManager.send(socket, messagePacket)
                            packetManager.send(socket, protocol.EndStreamPacket().setPacketType(protocol.Message64bytePacket))
                        #Target of unicast does not exist
                        else:
                            print(sender + " tried to send the following message to non-existent user " + messageReciever +": " + packet.getMessage())
                            toLog.put(sender + " tried to send the following message to non-existent user " + messageReciever +": " + packet.getMessage())
                            packetManager.send(clientsocket, protocol.NameNotFound16BytePacket().setName(messageReciever))
                    
                    #Reset variables in preparation for the next message
                    messageStream = ""
                    messageReciever = ""

            #Sent by the client when they want the list of available downloads
            elif (type(packet) == protocol.RequestDownloadListPacket):
                print(socketToName[clientsocket] + " requested download list")
                toLog.put(socketToName[clientsocket] + " requested download list")
                #Send a packet with the name of each download
                for fileName in os.listdir(os.curdir + os.sep + "download"):
                    packetManager.send(clientsocket, protocol.ProvideDownloadNamePacket().setName(fileName))
                #Send packet to signify there are no more downloads
                packetManager.send(clientsocket, protocol.EndStreamPacket().setPacketType(protocol.ProvideDownloadNamePacket))

            #Sent by client when they want to download a file
            elif (type(packet) == protocol.ProvideDownloadNamePacket):
                #Attempt to open the file specified by client
                try:
                    with open(os.curdir + os.sep + "download" + os.sep + packet.getName(), "rb") as binaryFile:
                        print(socketToName[clientsocket] + " requested the file " + packet.getName())
                        toLog.put(socketToName[clientsocket] + " requested the file " + packet.getName())

                        #Break file into chunks and send to client
                        packets = protocol.FileBinaryChunkPacket.toPackets(binaryFile.read())
                        for packet in packets:
                            packetManager.send(clientsocket, packet)
                        #Signifies there are no more chunks to send
                        packetManager.send(clientsocket, protocol.EndStreamPacket().setPacketType(protocol.FileBinaryChunkPacket))

                #File couldn't be found, send an error to client
                except FileNotFoundError:
                    packetManager.send(clientsocket, protocol.FileNotFoundPacket.setName(packet.getName()))
                    print("Client requested the file " + packet.getName() + " but it could not be found")
                    toLog.put("Client requested the file " + packet.getName() + " but it could not be found")

    #Client has disconnected or has sent an unrecognised packet
    except (RuntimeError, ConnectionResetError, protocol.UnrecognisedByteCodeException):
        name = socketToName.pop(clientsocket)
        nameToSocket.pop(name)
        print(name + " disconnected")
        toLog.put(name + " disconnected")

        #Let other clients know
        packet = protocol.Message64bytePacket().setMessage(name + " has left").setName("Server")
        for socket in socketToName.keys():
            packetManager.send(socket, packet)
            packetManager.send(socket, protocol.EndStreamPacket().setPacketType(protocol.Message64bytePacket))


print("starting server on port " + sys.argv[1])
with open("./server.log", "w") as file:
    file.write("")
toLog.put("Starting server on port " + sys.argv[1] + "...")

startServer()

