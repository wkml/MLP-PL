#!/bin/bash

# Make for COCOAPI
# cd cocoapi/PythonAPI
# make -j8
# cd ../..

cd ..

post='SSGRL-ls_0-p1_0-eps0_1-epoch20-fastfix'
printFreq=800

mode='SSGRL'
dataset='COCO2014'
prob=1.0
eps=0.1
method=0

pretrainedModel='/data1/2022_stu/wikim_exp/mlp-pl/data/checkpoint/resnet101.pth'
resumeModel='None'
# resumeModel='exp/checkpoint/SST_pro-COCO-baseline1-p0.2/Checkpoint_Best.pth'
# resumeModel='exp/checkpoint/origin/Checkpoint_Best.pth'
evaluate='False'

epochs=20
startEpoch=0
stepEpoch=15

batchSize=16
lr=1e-5
momentum=0.9
weightDecay=5e-4

cropSize=448
scaleSize=512
workers=8

generateLabelEpoch=5

intraBCEWeight=1.0
intraBCEMargin=0.95
intraCooccurrenceWeight=10.0

interBCEWeight=1.0
interBCEMargin=0.95
interDistanceWeight=0.05
interExampleNumber=100

interPrototypeDistanceWeight=0.05
prototypeNumber=10
useRecomputePrototype='True'
computePrototypeEpoch=5

OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 CUDA_VISIBLE_DEVICES=0 python SSGRL_confidence.py \
    --post ${post} \
    --printFreq ${printFreq} \
    --mode ${mode} \
    --dataset ${dataset} \
    --prob ${prob} \
    --eps ${eps} \
    --method ${method} \
    --pretrainedModel ${pretrainedModel} \
    --resumeModel ${resumeModel} \
    --evaluate ${evaluate} \
    --epochs ${epochs} \
    --startEpoch ${startEpoch} \
    --stepEpoch ${stepEpoch} \
    --batchSize ${batchSize} \
    --lr ${lr} \
    --momentum ${momentum} \
    --weightDecay ${weightDecay} \
    --cropSize ${cropSize} \
    --scaleSize ${scaleSize} \
    --workers ${workers} \
    --generateLabelEpoch ${generateLabelEpoch} \
    --intraBCEMargin ${intraBCEMargin} \
    --intraBCEWeight ${intraBCEWeight} \
    --intraCooccurrenceWeight ${intraCooccurrenceWeight} \
    --interBCEWeight ${interBCEWeight} \
    --interBCEMargin ${interBCEMargin} \
    --interDistanceWeight ${interDistanceWeight} \
    --interExampleNumber ${interExampleNumber} \
    --interPrototypeDistanceWeight ${interPrototypeDistanceWeight} \
    --prototypeNumber ${prototypeNumber} \
    --useRecomputePrototype ${useRecomputePrototype} \
    --computePrototypeEpoch ${computePrototypeEpoch}