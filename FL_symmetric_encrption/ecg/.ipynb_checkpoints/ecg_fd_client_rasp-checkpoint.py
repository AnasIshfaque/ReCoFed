#!/usr/bin/env python
# coding: utf-8

# # ECG Federated 1D-CNN Client Side
# This code is the server part of ECG federated 1D-CNN model for **multi** client and a server.

users = 3 # number of clients

import os
import h5py

import socket
import struct
import pickle

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

from torch.utils.data import Dataset, DataLoader
from torch.optim import Adam

from Crypto.Cipher import AES

import time

from tqdm import tqdm


def getFreeDescription():
    free = os.popen("free -h")
    i = 0
    while True:
        i = i + 1
        line = free.readline()
        if i == 1:
            return (line.split()[0:7])


def getFree():
    free = os.popen("free -h")
    i = 0
    while True:
        i = i + 1
        line = free.readline()
        if i == 2:
            return (line.split()[0:7])

from gpiozero import CPUTemperature

def printPerformance():
    cpu = CPUTemperature()

    print("temperature: " + str(cpu.temperature))

    description = getFreeDescription()
    mem = getFree()

    print(description[0] + " : " + mem[1])
    print(description[1] + " : " + mem[2])
    print(description[2] + " : " + mem[3])
    print(description[3] + " : " + mem[4])
    print(description[4] + " : " + mem[5])
    print(description[5] + " : " + mem[6])

printPerformance()

root_path = '../../datasets/'

# setting key and nonce of 16 bytes
key = b"FedLwithHEandIoT"
nonce = b"FedLwithHEandIoT"

# device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
device = "cpu"
print(device)

client_order = int(input("client_order(start from 0): "))

num_traindata = 13244 // users

# Data load

class ECG(Dataset):
    def __init__(self, train=True):
        if train:
            # total: 13244
            with h5py.File(os.path.join(root_path, 'ecg_data', 'train_ecg.hdf5'), 'r') as hdf:
                self.x = hdf['x_train'][num_traindata * client_order : num_traindata * (client_order + 1)]
                self.y = hdf['y_train'][num_traindata * client_order : num_traindata * (client_order + 1)]

        else:
            with h5py.File(os.path.join(root_path, 'ecg_data', 'test_ecg.hdf5'), 'r') as hdf:
                self.x = hdf['x_test'][:]
                self.y = hdf['y_test'][:]
    
    def __len__(self):
        return len(self.x)
    
    def __getitem__(self, idx):
        return torch.tensor(self.x[idx], dtype=torch.float), torch.tensor(self.y[idx])

# Making Batch Generator

batch_size = 32


# `DataLoader` for batch generating
# `torch.utils.data.DataLoader(dataset, batch_size=1, shuffle=False)`

train_dataset = ECG(train=True)
test_dataset = ECG(train=False)
trainloader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
testloader = DataLoader(test_dataset, batch_size=batch_size)

# Number of total batches
train_total_batch = len(trainloader)
print(train_total_batch)
test_batch = len(testloader)
print(test_batch)

class EcgConv1d(nn.Module):
    def __init__(self):
        super(EcgConv1d, self).__init__()        
        self.conv1 = nn.Conv1d(1, 16, 7)  # 124 x 16        
        self.relu1 = nn.LeakyReLU()
        self.pool1 = nn.MaxPool1d(2)  # 62 x 16
        self.conv2 = nn.Conv1d(16, 16, 5)  # 58 x 16
        self.relu2 = nn.LeakyReLU()        
        self.conv3 = nn.Conv1d(16, 16, 5)  # 54 x 16
        self.relu3 = nn.LeakyReLU()        
        self.conv4 = nn.Conv1d(16, 16, 5)  # 50 x 16
        self.relu4 = nn.LeakyReLU()
        self.pool4 = nn.MaxPool1d(2)  # 25 x 16
        self.linear5 = nn.Linear(25 * 16, 128)
        self.relu5 = nn.LeakyReLU()        
        self.linear6 = nn.Linear(128, 5)
        self.softmax6 = nn.Softmax(dim=1)
    
    def forward(self, x):
        x = self.conv1(x)
        x = self.relu1(x)
        x = self.pool1(x)        
        x = self.conv2(x)
        x = self.relu2(x)        
        x = self.conv3(x)
        x = self.relu3(x)        
        x = self.conv4(x)
        x = self.relu4(x)
        x = self.pool4(x)
        x = x.view(-1, 25 * 16)
        x = self.linear5(x)
        x = self.relu5(x)        
        x = self.linear6(x)
        x = self.softmax6(x)
        return x        

ecg_net = EcgConv1d()
ecg_net.to(device)

criterion = nn.CrossEntropyLoss()
rounds = 100 # default
local_epochs = 1 # default
lr = 0.001
optimizer = Adam(ecg_net.parameters(), lr=lr)

# Socket initialization
# Required socket functions

def send_msg(sock, msg, encrypt=True):
    # prefix each message with a 4-byte length in network byte order
    msg = pickle.dumps(msg)

    if encrypt == True:
        # instantiating the crypto engine
        engine = AES.new(key, AES.MODE_EAX, nonce)
        msg = engine.encrypt(msg)
    
    msg = struct.pack('>I', len(msg)) + msg
    sock.sendall(msg)

def recv_msg(sock):
    # read message length and unpack it into an integer
    raw_msglen = recvall(sock, 4, False)
    if not raw_msglen:
        return None
        
    msglen = struct.unpack('>I', raw_msglen)[0]
    # read the message data
    msg =  recvall(sock, msglen)
    msg = pickle.loads(msg)
    return msg

def recvall(sock, n, decrypt=True):
    # helper function to receive n bytes or return None if EOF is hit
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet

    if decrypt == True:
        engine = AES.new(key, AES.MODE_EAX, nonce)
        data = engine.decrypt(data)
        
    return data

printPerformance()

# Set host address and port number

host = input("IP address: ")
port = 10080
max_recv = 100000

# Open the client socket

s = socket.socket()
s.connect((host, port))

# SET TIMER

start_time = time.time()    # store start time
print("timmer start!")

msg = recv_msg(s)
rounds = msg['rounds'] 
client_id = msg['client_id']
local_epochs = msg['local_epoch']
send_msg(s, len(train_dataset))

# update weights from server
# train
for r in range(rounds):  # loop over the dataset multiple times
    weights = recv_msg(s)
    ecg_net.load_state_dict(weights)
    ecg_net.eval()
    for local_epoch in range(local_epochs):
        
        for i, data in enumerate(tqdm(trainloader, ncols=100, desc='Round '+str(r+1)+'_'+str(local_epoch+1))):
            
            # get the inputs; data is a list of [inputs, labels]
            inputs, labels = data
            inputs = inputs.to(device)
            labels = labels.clone().detach().long().to(device)

            # zero the parameter gradients
            optimizer.zero_grad()

            # forward + backward + optimize
            outputs = ecg_net(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

    msg = ecg_net.state_dict()
    send_msg(s, msg)

print('Finished Training')

printPerformance()

end_time = time.time()  #store end time
print("Training Time: {} sec".format(end_time - start_time))
