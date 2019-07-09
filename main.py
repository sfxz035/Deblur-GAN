import tensorflow as tf
import dataset
import network.model as model
import numpy as np
import os
import argparse
import cv2 as cv
import scipy.misc

from utils.compute import *
os.environ["CUDA_VISIBLE_DEVICES"] = '1'   #指定第一块GPU可用
config = tf.ConfigProto()
config.gpu_options.per_process_gpu_memory_fraction = 1 # 程序最多只能占用指定gpu50%的显存
config.gpu_options.allow_growth = True      #程序按需申请内存
sess = tf.InteractiveSession(config = config)


parser = argparse.ArgumentParser()
parser.add_argument("--train_file",default="./data_blur/train")
parser.add_argument("--test_file",default="./data_blur/test")
parser.add_argument("--batch_size",default=1,type=int)
parser.add_argument("--savenet_path",default='./libSaveNet/savenet/')
parser.add_argument("--vgg_ckpt",default='./libSaveNet/vgg_ckpt/vgg_19.ckpt')
parser.add_argument("--epoch",default=200000,type=int)
parser.add_argument("--learning_rate",default=0.0001,type=float)
parser.add_argument("--crop_size",default=256,type=int)
parser.add_argument("--num_train",default=10000,type=int)
parser.add_argument("--num_test",default=1500,type=int)
parser.add_argument("--EPS",default=1e-12,type=float)
parser.add_argument("--perceptual_mode",default='VGG33')

parser.add_argument("--num_of_down_scale", type = int, default = 2)
parser.add_argument("--gen_resblocks", type = int, default = 9)
parser.add_argument("--n_feats", type = int, default = 64)
parser.add_argument("--discrim_blocks", type = int, default = 3)

args = parser.parse_args()

def GAN_train(args):

    x_train, y_train = dataset.load_imgs_label(args.train_file, crop_size=args.crop_size,min=15000)
    x_test, y_test = dataset.load_imgs_label(args.test_file, crop_size=args.crop_size,min=150)

    genInput = tf.placeholder(tf.float32,shape = [args.batch_size,args.crop_size,args.crop_size,3])
    genLabel = tf.placeholder(tf.float32,shape = [args.batch_size,args.crop_size,args.crop_size,3])
    genOutput = model.generator(genInput,args=args,name='generator')

    discr_outlabel = model.discriminator(genLabel,args=args,name='discriminator')
    discr_outGenout = model.discriminator(genOutput,args=args,reuse=True,name='discriminator')

    # gen_loss = model.gen_loss(genOutput,genLabel,discr_outGenout,args.EPS,args.perceptual_mode)
    # dis_loss = model.discr_loss(discr_outGenout,discr_outlabel,args.EPS)
    gen_loss = model.gen_loss(genOutput,genLabel,discr_outGenout,args.EPS,args.perceptual_mode)
    dis_loss = model.discr_loss(discr_outGenout,discr_outlabel)+10*model.GP_loss(genInput,genLabel,args=args)

    PSNR = compute_psnr(genOutput,genLabel,convert=True)

    tf.summary.scalar('genloss', gen_loss)
    tf.summary.scalar('disloss', dis_loss)
    tf.summary.scalar('PSNR', PSNR)
    summary_op = tf.summary.merge_all()

    var_list = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)
    saver = tf.train.Saver(var_list,max_to_keep=10)
    # var_list = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='generator') + \
    #             tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='discriminator')
    genvar_list = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='generator')
    disvar_list = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='discriminator')
    gensave = tf.train.Saver(genvar_list,max_to_keep=10)
    dissave = tf.train.Saver(disvar_list,max_to_keep=10)

    gen_updates_op = tf.group(*tf.get_collection(tf.GraphKeys.UPDATE_OPS,scope='generator'))
    with tf.control_dependencies([gen_updates_op]):
        gentrain_step = tf.train.AdamOptimizer(args.learning_rate).minimize(gen_loss,var_list=genvar_list)
    dis_updates_op = tf.group(*tf.get_collection(tf.GraphKeys.UPDATE_OPS,scope='discriminator'))
    with tf.control_dependencies([dis_updates_op]):
        distrain_step = tf.train.AdamOptimizer(args.learning_rate).minimize(dis_loss,var_list=disvar_list)

    vgg_var_list = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='vgg_19')
    vgg_restore = tf.train.Saver(vgg_var_list)

    train_writer = tf.summary.FileWriter('./my_graph/train', sess.graph)
    test_writer = tf.summary.FileWriter('./my_graph/test')
    tf.global_variables_initializer().run()

    vgg_restore.restore(sess, args.vgg_ckpt)
    # last_file = tf.train.latest_checkpoint(args.savenet_path)
    # if last_file:
    #     saver.restore(sess, last_file)
    count, m = 0, 0
    for ep in range(args.epoch):
        batch_idxs = len(x_train) // args.batch_size
        for idx in range(batch_idxs):
            # batch_input = x_train[idx * args.batch_size: (idx + 1) * args.batch_size]
            # batch_labels = y_train[idx * args.batch_size: (idx + 1) * args.batch_size]
            batch_input, batch_labels = dataset.random_batch(x_train,y_train,args.batch_size)
            for i in range(2):
                sess.run(distrain_step, feed_dict={genInput: batch_input, genLabel: batch_labels})
            sess.run(gentrain_step, feed_dict={genInput: batch_input, genLabel: batch_labels})

            count += 1
            # print(count)
            if count % 100 == 0:
                m += 1
                batch_input_test, batch_labels_test = dataset.random_batch(x_test, y_test, args.batch_size)
                # batch_input_test = x_test[0 : args.batch_size]
                # batch_labels_test = y_test[0 : args.batch_size]

                PSNR_train = sess.run(PSNR, feed_dict={genInput: batch_input,genLabel: batch_labels})
                PSNR_test = sess.run(PSNR, feed_dict={genInput: batch_input_test, genLabel: batch_labels_test})

                genloss_train = sess.run(gen_loss,feed_dict={genInput:batch_input,genLabel:batch_labels})
                disloss_train = sess.run(dis_loss,feed_dict={genInput:batch_input,genLabel:batch_labels})
                genloss_test = sess.run(gen_loss,feed_dict={genInput:batch_input_test,genLabel:batch_labels_test})
                disloss_test = sess.run(dis_loss,feed_dict={genInput:batch_input_test,genLabel:batch_labels_test})
                print("Epoch: %-5.2d step: %2d" % ((ep + 1), count),
                      "\n",'train/test_PSNR: %-12.8f' % PSNR_train,PSNR_test,
                      "\t", 'train/test_genloss: %-12.8f' % genloss_train,genloss_test,
                      "\t", 'train/test_disloss: %-12.8f' % disloss_train,disloss_test)
                train_writer.add_summary(sess.run(summary_op, feed_dict={genInput: batch_input, genLabel: batch_labels}), m)
                test_writer.add_summary(sess.run(summary_op, feed_dict={genInput: batch_input_test,
                                                                     genLabel: batch_labels_test}), m)
            if (count + 1) % 10000 == 0:
                saver.save(sess, os.path.join(args.savenet_path, 'GAN_net%d.ckpt-done' % (count)))
def adtest(args):
    savepath = './libSaveNet/savenet/GAN_net29999.ckpt-done'
    path_blur = './data_blur/valid/blur.png'
    path_sharp = './data_blur/valid/sharp.png'
    img_blur = cv.imread(path_blur)
    img = cv.imread(path_sharp)
    img_shape = np.shape(img)
    row,col = img_shape[0],img_shape[1]
    ## 归一化
    img_norm = img/ (255. / 2.) - 1
    img_blur_norm = img_blur / (255. / 2.) - 1

    img_blur_input = np.expand_dims(img_blur_norm,0)
    img_label = np.expand_dims(img_norm,0)
    x = tf.placeholder(tf.float32,shape = [1,row,col, 3])
    y_ = tf.placeholder(tf.float32,shape = [1,row,col,3])
    y = model.generator(x,args=args,name='generator')
    loss = tf.reduce_mean(tf.square(y - y_))
    PSNR = compute_psnr(y,y_,convert=True)
    variables_to_restore = []
    for v in tf.global_variables():
        variables_to_restore.append(v)
    saver = tf.train.Saver(variables_to_restore, write_version=tf.train.SaverDef.V2, max_to_keep=None)
    tf.global_variables_initializer().run()
    saver.restore(sess, savepath)
    output = sess.run(y,feed_dict={x:img_blur_input})

    loss_test = sess.run(loss,feed_dict={y:output,y_:img_label})
    PSNR_test = sess.run(PSNR,feed_dict={y:output,y_:img_label})


    np.save('./output/deblur_img.npy',output)
    # cv.imwrite('./output/sp_img.png',output,0)
    # cv.imwrite('./output/lr_img.png',img_LR,0)
    # cv.imwrite('./output/hr_img.png',img,0)
    print('loss_test:[%.8f],PSNR_test:[%.8f]' % (loss_test,PSNR_test))
def predict(args):
    savepath = './libSaveNet/savenet/GAN_net19999.ckpt-done'
    path_face = './data/valid/2019-04-18-09-33-59-828886_1.bmp'
    img = cv.imread(path_face)
    img = img / (255. / 2.) - 1
    img_shape = np.shape(img)
    img_input = np.expand_dims(img,0)
    x = tf.placeholder(tf.float32,shape = [1,img_shape[0],img_shape[1], 3])
    y = model.generator(x,args=args,name='generator')
    variables_to_restore = []
    for v in tf.global_variables():
        variables_to_restore.append(v)
    saver = tf.train.Saver(variables_to_restore, write_version=tf.train.SaverDef.V2, max_to_keep=None)
    tf.global_variables_initializer().run()
    saver.restore(sess, savepath)
    output = sess.run(y,feed_dict={x:img_input})
    np.save('./output/sp_img.npy',output)

if __name__ == '__main__':
    # GAN_train(args)
    adtest(args)
    # predict(args)