#!/usr/bin/env python
# coding: utf-8

# # CIFAR10 Federated Mobilenet Client Side
# This code is the server part of CIFAR10 federated mobilenet for **multi** client and a server.

# In[3]:


users = 3 # number of clients


# In[4]:


import os
import h5py
import numpy as np

import socket
import struct
import pickle

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
from torchvision import datasets,transforms,models
import torch.optim as optim

from torch.utils.data import Dataset, DataLoader

import time
import copy

from tqdm import tqdm


# In[2]:


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


# In[3]:


printPerformance()


# In[5]:


root_path = '../../datasets/THB_splitted'


# ## Cuda

# In[6]:


# device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
device = "cpu"
print(device)


# In[7]:


client_order = int(input("client_order(start from 0): "))


# In[8]:


num_traindata = 262 // users


# ## Data load

# In[9]:


# transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616))])

mean = np.array([0.485,0.456,0.406])
std = np.array([0.229,0.224,0.225])
transform = transforms.Compose([transforms.RandomResizedCrop(224),transforms.RandomHorizontalFlip(),transforms.ToTensor(),transforms.Normalize(mean,std)])

from torch.utils.data import Subset


indices = list(range(262))

lower_idx = num_traindata * client_order
upper_idx = num_traindata * (client_order + 1)

#giving the extra data instance to the last client
if (client_order+1 == users):
    upper_idx += 1
    
part_tr = indices[lower_idx : upper_idx]


# In[10]:


# trainset = torchvision.datasets.CIFAR10 (root=root_path, train=True, download=True, transform=transform)
trainset = datasets.ImageFolder(os.path.join(root_path,'train'), transform)

trainset_sub = Subset(trainset, part_tr)

print(f'trainset size: {len(trainset)}, trainset_sub: {len(trainset_sub)}')
train_loader = torch.utils.data.DataLoader(trainset_sub, batch_size=4, shuffle=True, num_workers=0)

# testset = torchvision.datasets.CIFAR10 (root=root_path, train=False, download=True, transform=transform)
# test_loader = torch.utils.data.DataLoader(testset, batch_size=4, shuffle=False, num_workers=0)


# In[11]:

# classes = ('plane', 'car', 'bird', 'cat', 'deer', 'dog', 'frog', 'horse', 'ship', 'truck')
classes = ('Bluetooth', 'Humidity', 'Transistor')

# ### Number of total batches

# In[13]:


train_total_batch = len(train_loader)
print(f'len(train_loader): {train_total_batch}')
# test_batch = len(test_loader)
# print(test_batch)

# -*- coding: utf-8 -*-
"""
Created on Thu Nov  1 14:23:31 2018
@author: tshzzz
"""

import torch
import torch.nn as nn

# In[15]:


sq_model = models.squeezenet1_1(weights=True)
sq_model.to(device)

#freezing previous layers
for param in sq_model.features.parameters():
    param.requires_grad = False

# modifying the last layer to match desired output class
num_classes = 3
in_ftrs = sq_model.classifier[1].in_channels
features = list(sq_model.classifier.children())[:-3] # Remove last 3 layers
features.extend([nn.Conv2d(in_ftrs, num_classes, kernel_size=1)]) # Add
features.extend([nn.ReLU(inplace=True)]) # Add
features.extend([nn.AdaptiveAvgPool2d(output_size=(1,1))]) # Add
sq_model.classifier = nn.Sequential(*features)

local_weights = copy.deepcopy(sq_model.state_dict())
# In[16]:


lr = 0.01
criterion = nn.CrossEntropyLoss()
optimizer = optim.SGD(sq_model.parameters(), lr=lr, momentum=0.9)

rounds = 400 # default
local_epochs = 1 # default


# ## Socket initialization
# ### Required socket functions

# In[17]:


def send_msg(sock, msg):
    # prefix each message with a 4-byte length in network byte order
    msg = pickle.dumps(msg)
    msg = struct.pack('>I', len(msg)) + msg
    # encrypt msg
    sock.sendall(msg)

def recv_msg(sock):
    # read message length and unpack it into an integer
    raw_msglen = recvall(sock, 4)
    if not raw_msglen:
        return None
    msglen = struct.unpack('>I', raw_msglen)[0]
    # read the message data
    msg =  recvall(sock, msglen)
    msg = pickle.loads(msg)
    return msg

def recvall(sock, n):
    # helper function to receive n bytes or return None if EOF is hit
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        # decrypt
        if not packet:
            return None
        data += packet
    return data


# In[15]:


printPerformance()


# ### Set host address and port number

# In[18]:


host = input("IP address: ")
port = 10080
max_recv = 100000


# ### Open the client socket

# In[19]:


s = socket.socket()
s.connect((host, port))


# ## SET TIMER

# In[20]:


start_time = time.time()    # store start time
print("timmer start!")


# In[21]:


msg = recv_msg(s)
rounds = msg['rounds'] 
client_id = msg['client_id']
local_epochs = msg['local_epoch']
send_msg(s, len(trainset_sub))


# In[22]:


# update weights from server
# train
for r in range(rounds):  # loop over the dataset multiple times
    
    last_layer_list = recv_msg(s)
    # Updating the global weight's last layer
    local_weights['classifier.1.weight'] = last_layer_list[0]
    local_weights['classifier.1.bias'] = last_layer_list[1]
    sq_model.load_state_dict(local_weights)
    sq_model.train()
    for local_epoch in range(local_epochs):
        
        for i, data in enumerate(tqdm(train_loader, ncols=100, desc='Round '+str(r+1)+'_'+str(local_epoch+1))):
            
            # get the inputs; data is a list of [inputs, labels]
            inputs, labels = data
            inputs = inputs.to(device)
            labels = labels.to(device)

            # zero the parameter gradients
            optimizer.zero_grad()

            # forward + backward + optimize
            outputs = sq_model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
    msg = [sq_model.state_dict()['classifier.1.weight'], sq_model.state_dict()['classifier.1.bias']]
    # msg = mobile_net.state_dict()
    send_msg(s, msg)

print('Finished Training')


# In[ ]:


printPerformance()


# In[23]:


end_time = time.time()  #store end time
print("Training Time: {} sec".format(end_time - start_time))


# In[ ]:




