import numpy as np

import torch
import torch.nn as nn

from .backbone.resnet import resnet101
from .GraphNeuralNetwork import GatedGNN
from .SemanticDecoupling import SemanticDecoupling
from .Element_Wise_Layer import Element_Wise_Layer

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

class SSGRL(nn.Module):
    def __init__(self, adjacencyMatrix, wordFeatures,
                 imageFeatureDim=2048, intermediaDim=1024, outputDim=2048,
                 classNum=80, wordFeatureDim=300, timeStep=3):

        super(SSGRL, self).__init__()

        self.backbone = resnet101()

        self.classNum = classNum
        self.timeStep = timeStep

        self.outputDim = outputDim
        self.intermediaDim = intermediaDim
        self.wordFeatureDim = wordFeatureDim
        self.imageFeatureDim = imageFeatureDim
        
        self.wordFeatures = self.load_features(wordFeatures)
        self.inMatrix, self.outMatrix = self.load_matrix(adjacencyMatrix)

        self.SemanticDecoupling = SemanticDecoupling(self.classNum, self.imageFeatureDim, self.wordFeatureDim, intermediaDim=self.intermediaDim)
        self.GraphNeuralNetwork = GatedGNN(self.imageFeatureDim, self.timeStep, self.inMatrix, self.outMatrix)

        self.fc = nn.Linear(2 * self.imageFeatureDim, self.outputDim)
        self.classifiers = Element_Wise_Layer(self.classNum, self.outputDim)

        self.relu = nn.ReLU(inplace=True)

        self.intraConcatIndex = self.getConcatIndex(self.classNum)
        self.intra_fc_1 = nn.Linear(self.imageFeatureDim, self.intermediaDim)
        self.intra_fc_2 = nn.Linear(2 * self.intermediaDim, self.outputDim)
        self.intra_fc_3 = nn.Linear(self.outputDim, self.outputDim)
        self.intra_classifiers = Element_Wise_Layer(sum([i for i in range(self.classNum)]), self.outputDim)

    def forward(self, input):
        batchSize = input.size(0)

        featureMap = self.backbone(input)                                            # (BatchSize, Channel, imgSize, imgSize)

        semanticFeature = self.SemanticDecoupling(featureMap, self.wordFeatures)[0]  # (BatchSize, classNum, imgFeatureDim)
        feature = self.GraphNeuralNetwork(semanticFeature)                           # (BatchSize, classNum, imgFeatureDim)
        
        # Predict Category
        output = torch.tanh(self.fc(torch.cat((feature.view(batchSize * self.classNum, -1),
                                               semanticFeature.view(-1, self.imageFeatureDim)),1)))

        output = output.contiguous().view(batchSize, self.classNum, self.outputDim)
        result = self.classifiers(output)                                            # (BatchSize, classNum)

        # Predict Co-occurrence
        intraFeature = self.intra_fc_1(semanticFeature)
        intraFeature = torch.cat((intraFeature[:, self.intraConcatIndex[0], :],
                                  intraFeature[:, self.intraConcatIndex[1], :]), 2)  # (BatchSize, \sum_{i=1}^{classNum-1}{i}, 2 * intermediaDim)
        output = self.relu(self.intra_fc_2(intraFeature))                            # (BatchSize, \sum_{i=1}^{classNum-1}{i}, outputDim)
        output = self.intra_fc_3(output)                                             # (BatchSize, \sum_{i=1}^{classNum-1}{i}, outputDim)
        intraCoOccurrence = self.intra_classifiers(output)

        return result, intraCoOccurrence

    def getConcatIndex(self, classNum):
        res = [[], []]
        for index in range(classNum-1):
            res[0] += [index for i in range(classNum-index-1)]
            res[1] += [i for i in range(index+1, classNum)]
        return res

    def load_features(self, wordFeatures):
        return nn.Parameter(torch.from_numpy(wordFeatures.astype(np.float32)), requires_grad=False)

    def load_matrix(self, mat):
        _in_matrix, _out_matrix = mat.astype(np.float32), mat.T.astype(np.float32)
        _in_matrix, _out_matrix = nn.Parameter(torch.from_numpy(_in_matrix), requires_grad=False), nn.Parameter(torch.from_numpy(_out_matrix), requires_grad=False)
        return _in_matrix, _out_matrix

# =============================================================================
# Help Functions
# =============================================================================
