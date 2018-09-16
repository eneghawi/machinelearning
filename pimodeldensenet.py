import numpy as np
import tensorflow as tf
from keras.utils import np_utils
from pathlib import Path
import shutil
import random
import time
import _pickle as cPickle

import densenet1

start = time.time()

# Delete old data and event summaries
dir1 = 'tf_model_data/pi_model_cifar10/'
path1 = Path(dir1)
dir2 = 'tensorboard/pi_model_cifar10/'
path2 = Path(dir2)
if path1.is_dir():
    shutil.rmtree(dir1)
if path2.is_dir():
    shutil.rmtree(dir2)


def unpickle(file):
    import pickle
    with open(file, 'rb') as fo:
        dict = pickle.load(fo, encoding='bytes')
    return dict

# 'data_batch_1' contains 10,000 CIFAR-10 images and their labels
file1 = 'cifar-10-batches-py/data_batch_1'
data_batch_1 = unpickle(file1)
print(list(data_batch_1.keys()))
X_train = np.array(data_batch_1[b'data'], dtype=np.float32)[:4000]
y_train = np_utils.to_categorical(data_batch_1[b'labels'])[:4000]

X_train=np.reshape(X_train,(-1,32,32,3))

# Training Parameters
lr_max = 0.003
w_max = 100
beta1 = 0.9
beta2 = 0.999
alpha = 0.15
beta = 0.01

# Split data and labels into mini-batches
batch_size = 100
total_batch = len(X_train) // batch_size
X_batches = np.array_split(X_train, total_batch)
Y_batches = np.array_split(y_train, total_batch)

# Training & displaying steps
num_steps = 300
display_step = 15

# Network Parameters
num_input = X_train.shape[1]  # CIFAR-10 data input (img shape: 32*32*3)
num_classes = y_train.shape[1]  # CIFAR-10 total classes (0-9 digits)

# tf Graph input
X = tf.placeholder(tf.float32, [None, 32,32,3], name='data')
Y = tf.placeholder(tf.float32, [None, num_classes], name='labels')
keep_prob = tf.placeholder(tf.float32, name='dropout')  # dropout (keep probability)
learning_rate = tf.placeholder(tf.float32, name='learning_rate')
weight_t = tf.placeholder(tf.float32, name='weight_t')


# Create some wrappers for simplicity
def gaussian_noise_layer(x, std):
    noise = np.random.normal(0.0, std, (x.shape[0], x.shape[1],x.shape[2],x.shape[3]))
    return x + noise


def gaussian(amplitude, scale, t, scope):
    return amplitude * np.exp(-scale * (1 - t / scope) ** 2)


def random_translate(images):
    # randomly generate an operation flag
    flag = random.randrange(0, 3)
    if flag == 0:
        return tf.map_fn(lambda img: tf.image.random_flip_left_right(img), images)
    elif flag == 1:
        return tf.map_fn(lambda img: tf.image.random_flip_up_down(img), images)
    else:
        return tf.map_fn(lambda img: tf.image.rot90(img), images)


def leaky_relu(x, alpha):
    return tf.nn.relu(x) - alpha * tf.nn.relu(-x)


def batch_norm(x, epsilon=0.001):
    shape = x.shape
    last = len(shape) - 1
    axis = list(range(last))
    mean, var = tf.nn.moments(x, axis)
    scale = tf.Variable(tf.ones([shape[last]]))
    offset = tf.Variable(tf.zeros([shape[last]]))
    return tf.nn.batch_normalization(x, mean, var, offset, scale, epsilon)


def init_weights(shape):
    return tf.Variable(tf.truncated_normal(shape, 0.05, 0.05))

def init_biases(shape):
    return tf.Variable(tf.zeros(shape))

def conv2d(x, W, b, strides=1, padding='SAME'):
    # Conv2D wrapper, with bias and relu activation
    x = tf.nn.conv2d(x, W, strides=[1, strides, strides, 1], padding=padding)
    x = tf.nn.bias_add(x, b)
    return leaky_relu(x, 0.1)


def maxpool2d(x, k=2, dropout=0.5):
    # MaxPool2D wrapper
    return tf.nn.dropout(tf.nn.max_pool(x, ksize=[1, k, k, 1], strides=[1, k, k, 1],
                                        padding='SAME'), dropout)



# Initialize stddev of filter weights (Ref. "He et al. 2015")
def init_stddev(filter_size, num_filters):
    return (2 / (filter_size ** 2 * num_filters)) ** 0.5

# Store layers weight & bias
weights = {
    # 3x3 conv, 3 inputs, 128 outputs
    'wc1a': tf.Variable(tf.random_normal([3, 3, 3, 128], mean=0.0, stddev=init_stddev(3, 128)), name='wc1a'),
    # 3x3 conv, 128 inputs, 128 outputs
    'wc1b': tf.Variable(tf.random_normal([3, 3, 128, 128], mean=0.0, stddev=init_stddev(3, 128)), name='wc1b'),
    # 3x3 conv, 128 inputs, 128 outputs
    'wc1c': tf.Variable(tf.random_normal([3, 3, 128, 128], mean=0.0, stddev=init_stddev(3, 128)), name='wc1c'),
    # 3x3 conv, 128 inputs, 256 outputs
    'wc2a': tf.Variable(tf.random_normal([3, 3, 128, 256], mean=0.0, stddev=init_stddev(3, 256)), name='wc2a'),
    # 3x3 conv, 128 inputs, 256 outputs
    'wc2b': tf.Variable(tf.random_normal([3, 3, 256, 256], mean=0.0, stddev=init_stddev(3, 256)), name='wc2b'),
    # 3x3 conv, 128 inputs, 256 outputs
    'wc2c': tf.Variable(tf.random_normal([3, 3, 256, 256], mean=0.0, stddev=init_stddev(3, 256)), name='wc2c'),
    # 3x3 conv, 256 inputs, 512 outputs
    'wc3a': tf.Variable(tf.random_normal([3, 3, 256, 512], mean=0.0, stddev=init_stddev(3, 512)), name='wc3a'),
    # 1x1 conv, 512 inputs, 256 outputs
    'wc3b': tf.Variable(tf.random_normal([1, 1, 512, 256], mean=0.0, stddev=init_stddev(1, 256)), name='wc3b'),
    # 1x1 conv, 256 inputs, 128 outputs
    'wc3c': tf.Variable(tf.random_normal([1, 1, 256, 128], mean=0.0, stddev=init_stddev(1, 128)), name='wc3c'),
    # 1x1x128 inputs, 10 outputs (class prediction)
    'out': tf.Variable(tf.random_normal([1 * 1 * 128, num_classes], mean=0.0, stddev=0.01), name='w_out')
}

biases = {
    'bc1a': tf.Variable(tf.random_normal([128]), name='bc1a'),
    'bc1b': tf.Variable(tf.random_normal([128]), name='bc1b'),
    'bc1c': tf.Variable(tf.random_normal([128]), name='bc1c'),
    'bc2a': tf.Variable(tf.random_normal([256]), name='bc2a'),
    'bc2b': tf.Variable(tf.random_normal([256]), name='bc2b'),
    'bc2c': tf.Variable(tf.random_normal([256]), name='bc2c'),
    'bc3a': tf.Variable(tf.random_normal([512]), name='bc3a'),
    'bc3b': tf.Variable(tf.random_normal([256]), name='bc3b'),
    'bc3c': tf.Variable(tf.random_normal([128]), name='bc3c'),
    'out': tf.Variable(tf.random_normal([num_classes]), name='b_out')
}


'''
# Construct two parallel and identical computation graphs
z = conv_net(X, weights, biases, keep_prob)
z_ = conv_net(X, weights, biases, keep_prob)
'''

#X=np.reshape(X,(-1,32,32,3))

# Construct two parallel and identical computation graphs
training_flag = tf.placeholder(tf.bool)

z=densenet1.DenseNet(x=X, nb_blocks=2, filters=4, training=training_flag).model
z_=densenet1.DenseNet(x=X, nb_blocks=2, filters=4, training=training_flag).model


# Define loss and optimizer
loss_op = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=z,
                                                                 labels=Y))
loss_op = tf.reduce_mean(loss_op + weight_t * tf.losses.mean_squared_error(predictions=z_,
                                                                           labels=z))
optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate,
                                   beta1=beta1,
                                   beta2=beta2)
train_op = optimizer.minimize(loss_op)

# Evaluate model
prediction = tf.nn.softmax(z)
correct_pred = tf.equal(tf.argmax(prediction, 1), tf.argmax(Y, 1))
accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

model_path = 'tf_model_data/pi_model_cifar10/pi_model_cifar10.ckpt'

# Initialize the variables (i.e. assign their default value)
init = tf.global_variables_initializer()

# Add ops to save all the variables.
saver = tf.train.Saver()

# Start training
with tf.Session() as sess:

    # Run the initializer
    sess.run(init)

    # Initialize learning_rate and unsupervised weight
    lr = 0.
    w_t = 0.

    for step in range(1, num_steps + 1):

        # Reset loss and accuracy for current training step
        avg_loss = 0.
        avg_acc = 0.

        # Ramp up/down learning rate and unsupervised weight
        if step <= 80:
            lr = gaussian(lr_max, 5, step, 80)
            w_t = gaussian(w_max, 5, step, 80)
        elif step > 250:
            lr = gaussian(lr_max, 12.5, step - 200, 50)
            w_t = w_max
        else:
            lr = lr_max
            w_t = w_max

        # Loop over all batches
        for i in range(total_batch):
            batch_x, batch_y = X_batches[i], Y_batches[i]
            # Add Gaussian noise (stddev=0.15) to data
            batch_x = gaussian_noise_layer(batch_x, alpha)
            # Run optimization op (backprop), loss op and accuracy op
            _, loss, acc = sess.run([train_op, loss_op, accuracy], feed_dict={X: batch_x,
                                                                              Y: batch_y,
                                                                              keep_prob: 0.5,
                                                                              learning_rate: lr,
                                                                              training_flag:True,
                                                                              weight_t: w_t})
            # Compute average loss and accuracy
            avg_loss += loss / total_batch
            avg_acc += acc / total_batch

            print("Avg_Loss: ",avg_loss)
            print("Avg_Acc: ",avg_acc)
            
        # Display loss and accuracy per step
        if step % display_step == 0 or step == 1:
            print("Step " + str(step) +
                  ", Loss=" + "{:.4f}".format(avg_loss) +
                  ", Accuracy=" + "{:.4f}".format(avg_acc))

    # Stop timer
    end = time.time()
    print('\nOptimization Finished!'
          '\nTotal training time: {:.2f} {}'.format((end - start) / 60, 'minutes'))

    # Save model data to model_path
    save_path = saver.save(sess, model_path)
    print("Model saved in file: %s" % save_path)

    # Calculate loss and accuracy for 256 CIFAR-10 test images
    file_test = 'cifar-10-batches-py/test_batch'
    test_batch = unpickle(file_test)
    X_test = np.array(test_batch[b'data'], dtype=np.float32)
    y_test = np_utils.to_categorical(test_batch[b'labels'])
    loss, acc = sess.run([loss_op, accuracy], feed_dict={X: X_test[:256],
                                                         Y: y_test[:256],
                                                         keep_prob: 1.0,
                                                         weight_t: w_t})
    print("Testing Loss: " + "{:.4f}".format(loss)
          + ", Testing Accuracy: " + "{:.4f}".format(acc))