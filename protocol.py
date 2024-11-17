from __future__ import annotations
from typing import Type
from abc import ABC, ABCMeta, abstractmethod
from socket import socket

#Assigns a unique number for each packet so the type of packet can be identified on recieval 
#This number is always sent as the first byte of a transmission 
class PacketManager():

    #Create singleton
    _instance = None
    
    @staticmethod
    def getInstance():
        if (PacketManager._instance == None):
            PacketManager._instance = PacketManager()
        return PacketManager._instance

    #Register packets
    def __init__(self) -> None:
        self._packetRegistry = {}
        self.registerPacketType(EndStreamPacket, b'\x00')
        self.registerPacketType(SetName16BytePacket, b'\x01')
        self.registerPacketType(NameNotFound16BytePacket, b'\x02')
        self.registerPacketType(Message64bytePacket, b'\x03')
        self.registerPacketType(RequestDownloadListPacket, b'\x04')
        self.registerPacketType(ProvideDownloadNamePacket, b'\x05')
        self.registerPacketType(FileNotFoundPacket, b'\x06')
        self.registerPacketType(FileBinaryChunkPacket, b'\x07')

    #Add packet to registry and make sure there are no collisions
    def registerPacketType(self, packetClass: Type[Packet], byteCode: bytes) -> None:
        if (packetClass in self._packetRegistry):
            raise PacketRegisteredException(packetClass, byteCode)
        if (byteCode in self._packetRegistry):
            raise ByteCodeUsedException(packetClass, byteCode)
        
        self._packetRegistry[byteCode] = packetClass
        self._packetRegistry[packetClass] = byteCode
    
    #Return packet type based on identifier
    def getPacketType(self, byteCode: bytes) -> Type[Packet]:
        return self._packetRegistry[byteCode]
    
    #Return identifier based of packet type
    def getBytecode(self, packetClass: Type[Packet]) -> bytes:
        return self._packetRegistry[packetClass]
    
    #Send a packet to the specified socket
    def send(self, recieverSocket: socket, packet: Packet) -> None:
        #Check packet is registered
        if (type(packet) not in self._packetRegistry):
            raise KeyError("Tried to send an unregistered packet type " + type(packet).__name__)
        
        #Encode packet and check packet is correct length
        encoded = packet.encode()
        if (len(encoded) != type(packet).getLength()):
            raise RuntimeError("Malformed packet data")
        
        #Send raw binary to socket
        data = self._packetRegistry[type(packet)] + encoded
        totalSent = 0
        while totalSent < type(packet).getLength() + 1:
            sent = recieverSocket.send(data[totalSent:])
            if sent == 0:
                raise RuntimeError("socket connection broken")
            totalSent = totalSent + sent
    
    #Attempt to recieve a packet on the provided socket
    def recieve(self, socket: socket) -> Packet:
        #There should always be at least a byte to identify packet type
        try:
            byteCode = socket.recv(1)
        except ConnectionResetError as e:
            raise e
        #Socket has disconnected and is no longer sending information
        if (byteCode == b''):
            raise RuntimeError("socket connection broken")
        #Got sent a packet type which isn't registered
        if (byteCode not in self._packetRegistry):
            raise UnrecognisedByteCodeException(byteCode)
        
        #Identify packet type
        packetType = self._packetRegistry[byteCode]

        #Recieve binary
        chunks = []
        bytesRecieved = 0
        while bytesRecieved < packetType.getLength():
            chunk = socket.recv(packetType.getLength())
            if chunk == b'':
                raise RuntimeError("socket connection broken")
            chunks.append(chunk)
            bytesRecieved = bytesRecieved + len(chunk)
        #Convert binary into a packet and return
        return packetType.decode(b''.join(chunks))

#Error for when a packet type is registered twice
class PacketRegisteredException(Exception):
    def __init__(self, packetClass: Type[Packet], byteCode: bytes) -> None:
        self.packetClass = packetClass
        self.byteCode = byteCode
        super().__init__("Tried to register packet " + packetClass.__name__ + " when already registered")

#Error for when a unique identifier is used twice
class ByteCodeUsedException(Exception):
    def __init__(self, packetClass: Type[Packet], byteCode: bytes) -> None:
        self.packetClass = packetClass
        self.byteCode = byteCode
        super().__init__("Tried to register packet with byteCode " + byteCode + " but is already in use")

#Error for when a packet type is not registered
class UnrecognisedByteCodeException(Exception):
    def __init__(self, byteCode: bytes) -> None:
        self.byteCode = byteCode
        super().__init__("Recieved unrecognised packet of byteCode " + byteCode)


#Abstract base class for packet
class Packet(ABC):

    #return packet length
    @staticmethod
    @abstractmethod
    def getLength() -> int:
        pass

    #return an instance of specific packet
    @staticmethod
    @abstractmethod
    def decode(bytes: bytes) -> Packet:
        pass

    #returns packet data in raw bytes
    @abstractmethod
    def encode(self) -> bytes:
        pass

class EndStreamPacket(Packet):
    def __init__(self) -> None:
        self._type = EndStreamPacket
        super().__init__()
    
    def decode(bytes: bytes) -> EndStreamPacket:
        return EndStreamPacket().setPacketType(PacketManager.getInstance().getPacketType(bytes))

    def setPacketType(self, type: Type[Packet]) -> EndStreamPacket:
        self._type = type
        return self
    
    def getPacketType(self) -> Type[Packet]:
        return self._type

    def getLength() -> int:
        return 1
    
    def encode(self) -> bytes:
        return PacketManager.getInstance().getBytecode(self._type)

class SetName16BytePacket(Packet):
    _length = 16

    def __init__(self) -> None:
        super().__init__()

    def setName(self, name: str) -> SetName16BytePacket:
        if (len(name) > self._length):
            raise ValueError("Username can be at most " + str(self._length) + " characters")
        self._name = name + " " * (self._length - len(name))
        return self
    
    def getName(self) -> str:
        return self._name.strip()

    def decode(bytes : bytes) -> SetName16BytePacket:
        return SetName16BytePacket().setName(bytes.decode())

    def getLength() -> int:
        return SetName16BytePacket._length
    
    def encode(self) -> bytes:
        return self._name.encode()
    
class NameNotFound16BytePacket(Packet):
    
    _length = 16

    def __init__(self) -> None:
        super().__init__()

    def setName(self, name: str) -> NameNotFound16BytePacket:
        if (len(name) > self._length):
            raise ValueError("Username can be at most " + str(self._length) + " characters")
        self._name = name + " " * (self._length - len(name))
        return self
    
    def getName(self) -> str:
        return self._name.strip()

    def decode(bytes : bytes) -> NameNotFound16BytePacket:
        return NameNotFound16BytePacket().setName(bytes.decode())

    def getLength() -> int:
        return NameNotFound16BytePacket._length
    
    def encode(self) -> bytes:
        return self._name.encode()

class Message64bytePacket(Packet):

    _nameLength = 16
    _messageLength = 64

    def __init__(self, name: str = "", message: str = "") -> None:
        self.setName(name)
        self.setMessage(message)
        super().__init__()

    def setName(self, name: str) -> Message64bytePacket:
        if (len(name) > self._nameLength):
            raise ValueError("Username can be at most " + str(self._nameLength) + " characters")
        self._name = name + " " * (self._nameLength - len(name))
        return self

    def setMessage(self, message: str) -> Message64bytePacket:
        if (len(message) > self._messageLength):
            raise ValueError("Message can be at most " + str(self._messageLength) + " characters")
        self._data = message + "\0" * (self._messageLength - len(message))
        return self

    def getName(self) -> str:
        return self._name.strip(" ")
    
    def getMessage(self) -> str:
        return self._data.strip("\0")

    def getLength() -> int:
        return Message64bytePacket._nameLength + Message64bytePacket._messageLength

    def decode(bytes : bytes) -> Message64bytePacket:
        return Message64bytePacket().setName(bytes[:Message64bytePacket._nameLength].decode()).setMessage(bytes[Message64bytePacket._nameLength:].decode())
    
    def encode(self) -> bytes:
        return self._name.encode() + self._data.encode()
    
    @staticmethod
    def toPackets(message : str) -> list[Message64bytePacket]:
        ret = []
        index = 0
        while index < len(message):
            ret.append(Message64bytePacket().setMessage(message[index : min(index + Message64bytePacket._messageLength, len(message))]))
            index += Message64bytePacket._messageLength
        return ret

class RequestDownloadListPacket(Packet):
    def __init__(self) -> None:
        super().__init__()
    
    def decode(bytes : bytes) -> RequestDownloadListPacket:
        return RequestDownloadListPacket()

    def getLength() -> int:
        return 0
    
    def encode(self) -> bytes:
        return b''

class ProvideDownloadNamePacket(Packet):

    _length = 2048

    def __init__(self) -> None:
        super().__init__()

    def setName(self, name: str) -> ProvideDownloadNamePacket:
        if (len(name) > self._length):
            raise ValueError("File name can be at most " + str(self._length) + " characters")
        self._name = name + " " * (self._length - len(name))
        return self
    
    def getName(self) -> str:
        return self._name.strip()

    def decode(bytes : bytes) -> ProvideDownloadNamePacket:
        return ProvideDownloadNamePacket().setName(bytes.decode())

    def getLength() -> int:
        return ProvideDownloadNamePacket._length
    
    def encode(self) -> bytes:
        return self._name.encode()

class FileNotFoundPacket(Packet):

    _length = 2048

    def __init__(self) -> None:
        super().__init__()

    def setName(self, name: str) -> FileNotFoundPacket:
        if (len(name) > self._length):
            raise ValueError("File name can be at most " + str(self._length) + " characters")
        self._name = name + " " * (self._length - len(name))
        return self
    
    def getName(self) -> str:
        return self._name.strip()

    def decode(bytes : bytes) -> FileNotFoundPacket:
        return FileNotFoundPacket().setName(bytes.decode())

    def getLength() -> int:
        return FileNotFoundPacket._length
    
    def encode(self) -> bytes:
        return self._name.encode()

class FileBinaryChunkPacket(Packet):

    _maxChunkSize = 2048
    _intSize = 2
    _length = _maxChunkSize + _intSize

    def __init__(self) -> None:
        self._data = b''
        self._chunkSize = 0
        super().__init__()

    def setData(self, data: bytes) -> FileBinaryChunkPacket:
        if (len(data) > self._maxChunkSize):
            raise ValueError("File chunk can be at most " + str(self._maxChunkSize) + " bytes")
        self._chunkSize = len(data)
        self._data = data + b'0' * (self._maxChunkSize - len(data))
        
        return self
    
    def getData(self) -> bytes:
        return self._data[:self._chunkSize]

    def decode(bytes : bytes) -> FileBinaryChunkPacket:
        high = int.from_bytes(bytes[:FileBinaryChunkPacket._intSize], "big") + FileBinaryChunkPacket._intSize
        return FileBinaryChunkPacket().setData(bytes[FileBinaryChunkPacket._intSize:high])

    def getLength() -> int:
        return FileBinaryChunkPacket._length
    
    def encode(self) -> bytes:
        return self._chunkSize.to_bytes(FileBinaryChunkPacket._intSize, "big") + self._data
    
    @staticmethod
    def toPackets(bytes: bytes) -> list[FileBinaryChunkPacket]:
        ret = []
        index = 0
        while index < len(bytes):
            ret.append(FileBinaryChunkPacket().setData(bytes[index : min(index + FileBinaryChunkPacket._maxChunkSize, len(bytes))]))
            index += FileBinaryChunkPacket._maxChunkSize
        return ret
