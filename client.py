import socket
import threading
import protocol
import select
import os
import sys
from queue import Queue

packetManager = protocol.PacketManager.getInstance()
if len(sys.argv) != 4:
    print("Expected 4 arguments, got", len(sys.argv))
    exit()
name = sys.argv[1]
downloadQueue = Queue()

#thread which runs in the background to handle recieving of packets
def packetReciever(clientSocket, stop_event):
    
    fileNames = []      #used to store incoming list of file names stream
    fileBinary = b''    #used to store incoming binary file stream
    messageStream = ""  #used to store incoming message stream
    messageSender = ""  #stores sender of incoming message stream


    #run until kill flag set from outside
    while not stop_event.is_set():

        #check if the socket has any data to recieve
        read, write, error = select.select([clientSocket], [], [], 0.1)
        for socket in read:
            #recieve packet and handle any errors
            try:
                packet = packetManager.recieve(socket)
            except protocol.UnrecognisedByteCodeException as e:
                print("Warning: recieved unrecognised packet from server - ignoring")
                continue
            except RuntimeError:
                print("Stopped recieving communications from server")
                return
            
            #check the type of packet which has been recieved
            if type(packet) == protocol.Message64bytePacket:    #message recieved
                messageStream += packet.getMessage()
                messageSender = packet.getName()

            elif type(packet) == protocol.NameNotFound16BytePacket: #message sent to a non-existent user
                print("Server could not find an online user by the name of " + packet.getName())

            elif type(packet) == protocol.FileNotFoundPacket:   #requested to download a file which doesn't exist
                print("Server could not find the requested file: " + packet.getName())

            elif type(packet) == protocol.ProvideDownloadNamePacket:    #recieved one fileName of the downloadable files list 
                fileNames.append(packet.getName())

            elif type(packet) == protocol.FileBinaryChunkPacket:    #recived a chunk of a file
                if (downloadQueue.empty()):
                    print("Server tried to provide a file when non was requested")
                    break
                fileBinary += packet.getData()  #build up file from the chunks

            elif type(packet) == protocol.EndStreamPacket:  #one of a variety of streams has ended
                if (packet.getPacketType() == protocol.Message64bytePacket):  #Finished sending download list
                    #printing out the now complete list of downloads
                    print(messageSender + ": " + messageStream)
                    messageStream = ""

                elif (packet.getPacketType() == protocol.ProvideDownloadNamePacket):  #Finished sending download list
                    #printing out the now complete list of downloads
                    print("The files available for download are:")
                    for fileName in fileNames:
                        print(fileName)
                    fileNames = []

                elif (packet.getPacketType() == protocol.FileBinaryChunkPacket):    #Finished sending a file
                    #saving the now assembled file
                    x = downloadQueue.get()
                    with open(x, "wb") as file:
                        file.write(fileBinary)
                        fileBinary = b''
                    print("File " + x + " was succesfully downloaded")


#open up socket and connected to the server
clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
clientsocket.connect((sys.argv[2], int(sys.argv[3])))

#open new thread to recieve packets
stop_event = threading.Event()
packetListen = threading.Thread(target=packetReciever, args=(clientsocket, stop_event,))
packetListen.start()

#set the username
packetManager.send(clientsocket, protocol.SetName16BytePacket().setName(name))


#continously listen for input from user
while True:
    value = input("")
    if value == "/quit":   #quit command issues
        break
    elif value == "/downloadList":
        packetManager.send(clientsocket, protocol.RequestDownloadListPacket())
        continue
    elif value.startswith("/download "):  #download command issued. Usage /download [downloadPath] [fileName]
        value = value.removeprefix("/download ")
        directoryPath = value.split(" ")[0]
        fileName = value.removeprefix(directoryPath + " ")

        #checks if entered directory exists
        if not os.path.exists(directoryPath):
            print("Download location could not be found, please make sure the directory exists")
            continue
        
        #file added to download queue
        print("Attempting to download file " + fileName + " to " + directoryPath)
        downloadQueue.put(directoryPath + os.sep + fileName)
        packetManager.send(clientsocket, protocol.ProvideDownloadNamePacket().setName(fileName))
        continue
    
    else:   #no command so just a regular message
    
        #check to see if a message is a broadcast. Usage: [target]message
        name = ""
        if (value.startswith("[")):
            for letter in value.removeprefix("["):
                if letter == "]":
                    value = value.removeprefix("[" + name + "]")
                    break
                name = name + letter

        #finish assembling packets and send
        packets = protocol.Message64bytePacket.toPackets(value)
        for packet in packets:
            packetManager.send(clientsocket, packet.setName(name))
        packetManager.send(clientsocket, protocol.EndStreamPacket().setPacketType(protocol.Message64bytePacket))

#exit sequence. Wait for packetlistening thread to end before closing the socket
stop_event.set()
packetListen.join()
clientsocket.shutdown(0)
clientsocket.close()