import sys
import time
import logging

from tensorboardX import SummaryWriter

import numpy as np
import torch
from torch import nn
import torch.optim
import torch.optim.lr_scheduler as lr_scheduler 

# from model.SST import SST
from model.SSGRL import SSGRL
# from model.SSGRL_origin import SSGRL
from loss.SST import BCELoss, intraAsymmetricLoss, ContrastiveLoss, getIntraPseudoLabel, getInterPseudoLabel

from utils.dataloader import get_graph_and_word_file, get_data_loader
from utils.metrics import AverageMeter, AveragePrecisionMeter, Compute_mAP_VOC2012
from utils.checkpoint import load_pretrained_model, save_code_file, save_checkpoint
from utils.ls import label_smoothing
from config import arg_parse, logger, show_args

global bestPrec
bestPrec = 0

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

def main():
    global bestPrec

    # Argument Parse
    args = arg_parse('SST')

    # Bulid Logger
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
    file_path = 'exp/log/{}.log'.format(args.post)
    file_handler = logging.FileHandler(file_path)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Show Argument
    show_args(args)

    # Save Code File
    save_code_file(args)

    # Create dataloader
    logger.info("==> Creating dataloader...")
    train_loader, test_loader = get_data_loader(args)
    logger.info("==> Done!\n")

    # Load the network
    logger.info("==> Loading the network...")
    GraphFile, WordFile = get_graph_and_word_file(args, train_loader.dataset.changedLabels)
    model = SSGRL(GraphFile, WordFile, classNum=args.classNum)

    if args.pretrainedModel != 'None':
        logger.info("==> Loading pretrained model...")
        model = load_pretrained_model(model, args)

    if args.resumeModel != 'None':
        logger.info("==> Loading checkpoint...")
        checkpoint = torch.load(args.resumeModel, map_location='cpu')
        bestPrec, args.startEpoch = checkpoint['best_mAP'], checkpoint['epoch']
        model.load_state_dict(checkpoint['state_dict'])
        logger.info("==> Checkpoint Epoch: {0}, mAP: {1}".format(args.startEpoch, bestPrec))

    model.to(device)
    logger.info("==> Done!\n")

    criterion = {'BCELoss': BCELoss(reduce=True, size_average=True).to(device),
                 'IntraCooccurrenceLoss' : intraAsymmetricLoss(args.classNum, gamma_neg=2, gamma_pos=1, reduce=True, size_average=True).to(device),
                 'BCEWithLogitsLoss': nn.BCEWithLogitsLoss(reduce=True, size_average=True).to(device)
                 }

    for p in model.backbone.parameters():
        p.requires_grad = False
    for p in model.backbone.layer4.parameters():
        p.requires_grad = True
    # optimizer = torch.optim.Adam(filter(lambda p : p.requires_grad, model.parameters()), lr=args.lr, weight_decay=args.weightDecay)
    optimizer = torch.optim.Adam(filter(lambda p : p.requires_grad, model.parameters()), lr=args.lr)

    scheduler = lr_scheduler.StepLR(optimizer, step_size=args.stepEpoch, gamma=0.1)

    if args.evaluate:
        Validate(test_loader, model, criterion, 0, args)
        return

    # if device == 'cuda':
    #     logger.info('Total: {:.3f} GB'.format(torch.cuda.get_device_properties(0).total_memory/1024.0**3))

    # Running Experiment
    logger.info("Run Experiment...")
    writer = SummaryWriter('{}/{}'.format('exp/summary/', args.post))

    for epoch in range(args.startEpoch, args.startEpoch + args.epochs):

        Train(train_loader, model, criterion, optimizer, writer, epoch, args)
        mAP = Validate(test_loader, model, criterion, epoch, args)

        scheduler.step()

        writer.add_scalar('mAP', mAP, epoch)
        
        # if device == 'cuda':
        #     torch.cuda.empty_cache()

        isBest, bestPrec = mAP > bestPrec, max(mAP, bestPrec)
        save_checkpoint(args, {'epoch':epoch, 'state_dict':model.state_dict(), 'best_mAP':mAP}, isBest)

        if isBest:
            logger.info('[Best] [Epoch {0}]: Best mAP is {1:.3f}'.format(epoch, bestPrec))

    writer.close()

def Train(train_loader, model, criterion, optimizer, writer, epoch, args):
    model.train()
    model.backbone.eval()
    model.backbone.layer4.train()

    loss, loss1, loss2, loss3, loss4, loss5 = AverageMeter(), AverageMeter(), AverageMeter(), AverageMeter(), AverageMeter(), AverageMeter()
    batch_time, data_time = AverageMeter(), AverageMeter()
    logger.info("=========================================")

    end = time.time()
    for batchIndex, (sampleIndex, input, target, groundTruth) in enumerate(train_loader):
        input, target = input.to(device), target.float().to(device)

        # Log time of loading data
        data_time.update(time.time() - end)

        # Forward
        output, intraCoOccurrence = model(input)

        # ls
        target = label_smoothing(groundTruth, '2', model.inMatrix)
        # torch.set_printoptions(sci_mode=False)
        # print(target)
        # target = label_smoothing(groundTruth, '3', intraCoOccurrence, epoch)
        # print("gt:",target_)

        # Compute and log loss
        # loss1_ = criterion['BCELoss'](output, target)
        # loss1_ = criterion['OriginLoss'](output, target_)

        # loss3_ = args.intraCooccurrenceWeight * criterion['IntraCooccurrenceLoss'](intraCoOccurrence, target) if epoch >= 1 else \
        #          args.intraCooccurrenceWeight * criterion['IntraCooccurrenceLoss'](intraCoOccurrence, target) * batchIndex / float(len(train_loader))

        # target[target < 0] = 0

        # target = ((1 - 0.1) * target) + ((0.1 * target.sum(axis=1)) / target.shape[1]).reshape(-1, 1)

        loss_ = criterion['BCEWithLogitsLoss'](output, target)

        loss.update(loss_.item(), input.size(0))
        # loss1.update(loss1_.item(), input.size(0))
        # loss3.update(loss3_.item(), input.size(0))

        # Backward
        loss_.backward()
        optimizer.step()
        optimizer.zero_grad()

        # Log time of batch
        batch_time.update(time.time() - end)
        end = time.time()

        if batchIndex % args.printFreq == 0:
            # logger.info('[Train] [Epoch {0}]: [{1:04d}/{2}] Batch Time {batch_time.avg:.3f} Data Time {data_time.avg:.3f}\n'
            #             '\t\t\t\t\tIntra Margin {intraMargin:.3f} Inter Margin {interMargin:.3f} Learn Rate {lr:.6f} BCE Loss {loss1.val:.4f} ({loss1.avg:.4f})\n'
            #             '\t\t\t\t\tIntra BCE Loss {loss2.val:.4f} ({loss2.avg:.4f}) Intra Co-occurrence Loss {loss3.val:.4f} ({loss3.avg:.4f})\n'
            #             '\t\t\t\t\tInter BCE Loss {loss4.val:.4f} ({loss4.avg:.4f}) Inter Distance Loss {loss5.val:.4f} ({loss5.avg:.4f})'.format(
            #             epoch, batchIndex, len(train_loader), batch_time=batch_time, data_time=data_time,
            #             intraMargin=args.intraBCEMargin, interMargin=args.interBCEMargin, lr=optimizer.param_groups[0]['lr'],
            #             loss1=loss1, loss2=loss2, loss3=loss3, loss4=loss4, loss5=loss5))
            # sys.stdout.flush()
            logger.info('[Train] [Epoch {0}]: [{1:04d}/{2}] Batch Time {batch_time.avg:.3f} Data Time {data_time.avg:.3f}\n'
                        '\t\t\t\t\tLearn Rate {lr:.6f} BCE Loss {loss.val:.4f} ({loss.avg:.4f})'.format(
                        epoch, batchIndex, len(train_loader), batch_time=batch_time, data_time=data_time,
                        lr=optimizer.param_groups[0]['lr'],
                        loss=loss))
            sys.stdout.flush()

    writer.add_scalar('Loss', loss.avg, epoch)
    writer.add_scalar('Loss_BCE', loss1.avg, epoch)
    writer.add_scalar('Loss_Intra_BCE', loss2.avg, epoch)
    writer.add_scalar('Loss_Intra_Cooccurrence', loss3.avg, epoch)
    writer.add_scalar('Loss_Inter_BCE', loss4.avg, epoch)
    writer.add_scalar('Loss_Inter_Distance', loss5.avg, epoch)

def Validate(val_loader, model, criterion, epoch, args):

    model.eval()

    apMeter = AveragePrecisionMeter()
    pred, loss, batch_time, data_time = [], AverageMeter(), AverageMeter(), AverageMeter()
    logger.info("=========================================")

    end = time.time()
    for batchIndex, (sampleIndex, input, target, groundTruth) in enumerate(val_loader):

        input, target = input.to(device), target.float().to(device)
        
        # Log time of loading data
        data_time.update(time.time() - end)

        # Forward
        with torch.no_grad():
            output, _ = model(input)

        target[target < 0] = 0

        # Compute loss and prediction
        loss_ = criterion['BCEWithLogitsLoss'](output, target)
        loss.update(loss_.item(), input.size(0))

        # Change target to [0, 1]
        # target[target < 0] = 0

        apMeter.add(output, target)
        pred.append(torch.cat((output, (target > 0).float()), 1))

        # Log time of batch
        batch_time.update(time.time() - end)
        end = time.time()

        # logger.info information of current batch        
        if batchIndex % args.printFreq == 0:
            logger.info('[Test] [Epoch {0}]: [{1:04d}/{2}] '
                        'Batch Time {batch_time.avg:.3f} Data Time {data_time.avg:.3f} '
                        'Loss {loss.val:.4f} ({loss.avg:.4f})'.format(
                epoch, batchIndex, len(val_loader),
                batch_time=batch_time, data_time=data_time,
                loss=loss))
            sys.stdout.flush()

    pred = torch.cat(pred, 0).cpu().clone().numpy()
    mAP = Compute_mAP_VOC2012(pred, args.classNum)

    averageAP = apMeter.value().mean()
    OP, OR, OF1, CP, CR, CF1 = apMeter.overall()
    OP_K, OR_K, OF1_K, CP_K, CR_K, CF1_K = apMeter.overall_topk(3)
    ACE, ECE, MCE = apMeter.calibration()

    logger.info('[Test] mAP: {mAP:.3f}, averageAP: {averageAP:.3f}\n'
                '\t\t\t\t(Compute with all label) OP: {OP:.3f}, OR: {OR:.3f}, OF1: {OF1:.3f}, CP: {CP:.3f}, CR: {CR:.3f}, CF1:{CF1:.3f}\n'
                '\t\t\t\t(Compute with top-3 label) OP: {OP_K:.3f}, OR: {OR_K:.3f}, OF1: {OF1_K:.3f}, CP: {CP_K:.3f}, CR: {CR_K:.3f}, CF1: {CF1_K:.3f}\n'
                '\t\t\t\tACE:{ACE:.6f}, ECE:{ECE:.6f}, MCE:{MCE:.6f}'.format(
                mAP=mAP, averageAP=averageAP,
                OP=OP, OR=OR, OF1=OF1, CP=CP, CR=CR, CF1=CF1, OP_K=OP_K, OR_K=OR_K, OF1_K=OF1_K, CP_K=CP_K, CR_K=CR_K, CF1_K=CF1_K,
                ACE=ACE, ECE=ECE, MCE=MCE))

    return mAP


if __name__=="__main__":
    main()