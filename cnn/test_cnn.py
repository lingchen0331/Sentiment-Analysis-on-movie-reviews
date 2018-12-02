# -*- coding:utf-8 -*-
__author__ = 'Randolph'

import os
import sys
import time
import tensorflow as tf
from utils import data_helpers as dh

# Parameters
# ==================================================

logger = dh.logger_fn('tflog', 'logs/test-{0}.log'.format(time.asctime()))

MODEL = input("Please input the model file you want to test, it should be like(1490175368): ")

while not (MODEL.isdigit() and len(MODEL) == 10):
    MODEL = input('The format of your input is illegal, it should be like(1490175368), please re-input: ')
logger.info('The format of your input is legal, now loading to next step...')

TRAININGSET_DIR = '../data/Train.json'
VALIDATIONSET_DIR = '../data/Validation.json'
TESTSET_DIR = '../data/Test.json'
MODEL_DIR = 'runs/' + MODEL + '/checkpoints/'
SAVE_DIR = 'results/' + MODEL

# Data Parameters
tf.flags.DEFINE_string("training_data_file", TRAININGSET_DIR, "Data source for the training data.")
tf.flags.DEFINE_string("validation_data_file", VALIDATIONSET_DIR, "Data source for the validation data")
tf.flags.DEFINE_string("test_data_file", TESTSET_DIR, "Data source for the test data")
tf.flags.DEFINE_string("checkpoint_dir", MODEL_DIR, "Checkpoint directory from training run")

# Model Hyperparameters
tf.flags.DEFINE_integer("pad_seq_len", 100, "Recommended padding Sequence length of data (depends on the data)")
tf.flags.DEFINE_integer("embedding_dim", 100, "Dimensionality of character embedding (default: 128)")
tf.flags.DEFINE_integer("embedding_type", 1, "The embedding type (default: 1)")
tf.flags.DEFINE_integer("fc_hidden_size", 1024, "Hidden size for fully connected layer (default: 1024)")
tf.flags.DEFINE_string("filter_sizes", "3,4,5", "Comma-separated filter sizes (default: '3,4,5')")
tf.flags.DEFINE_integer("num_filters", 128, "Number of filters per filter size (default: 128)")
tf.flags.DEFINE_float("dropout_keep_prob", 0.5, "Dropout keep probability (default: 0.5)")
tf.flags.DEFINE_float("l2_reg_lambda", 0.0, "L2 regularization lambda (default: 0.0)")
tf.flags.DEFINE_integer("num_classes", 367, "Number of labels (depends on the task)")
tf.flags.DEFINE_integer("top_num", 5, "Number of top K prediction classes (default: 5)")
tf.flags.DEFINE_float("threshold", 0.5, "Threshold for prediction classes (default: 0.5)")

# Test Parameters
tf.flags.DEFINE_integer("batch_size", 512, "Batch Size (default: 1)")

# Misc Parameters
tf.flags.DEFINE_boolean("allow_soft_placement", True, "Allow device soft device placement")
tf.flags.DEFINE_boolean("log_device_placement", False, "Log placement of ops on devices")
tf.flags.DEFINE_boolean("gpu_options_allow_growth", True, "Allow gpu options growth")

FLAGS = tf.flags.FLAGS
FLAGS(sys.argv)
dilim = '-' * 100
logger.info('\n'.join([dilim, *['{0:>50}|{1:<50}'.format(attr.upper(), FLAGS.__getattr__(attr))
                                for attr in sorted(FLAGS.__dict__['__wrapped'])], dilim]))


def test_cnn():
    """Test CNN model."""

    # Load data
    logger.info("Loading data...")
    logger.info('Recommended padding Sequence length is: {0}'.format(FLAGS.pad_seq_len))

    logger.info('Test data processing...')
    test_data = dh.load_data_and_labels(FLAGS.test_data_file, FLAGS.num_classes,
                                        FLAGS.embedding_dim, data_aug_flag=False)

    logger.info('Test data padding...')
    x_test, y_test = dh.pad_data(test_data, FLAGS.pad_seq_len)
    y_test_labels = test_data.labels

    # Load cnn model
    logger.info("Loading model...")
    checkpoint_file = tf.train.latest_checkpoint(FLAGS.checkpoint_dir)
    logger.info(checkpoint_file)

    graph = tf.Graph()
    with graph.as_default():
        session_conf = tf.ConfigProto(
            allow_soft_placement=FLAGS.allow_soft_placement,
            log_device_placement=FLAGS.log_device_placement)
        session_conf.gpu_options.allow_growth = FLAGS.gpu_options_allow_growth
        sess = tf.Session(config=session_conf)
        with sess.as_default():
            # Load the saved meta graph and restore variables
            saver = tf.train.import_meta_graph("{0}.meta".format(checkpoint_file))
            saver.restore(sess, checkpoint_file)

            # Get the placeholders from the graph by name
            input_x = graph.get_operation_by_name("input_x").outputs[0]
            input_y = graph.get_operation_by_name("input_y").outputs[0]
            dropout_keep_prob = graph.get_operation_by_name("dropout_keep_prob").outputs[0]
            is_training = graph.get_operation_by_name("is_training").outputs[0]

            # Tensors we want to evaluate
            scores = graph.get_operation_by_name("output/scores").outputs[0]
            loss = graph.get_operation_by_name("loss/loss").outputs[0]

            # Split the output nodes name by '|' if you have several output nodes
            output_node_names = 'output/logits|output/scores'

            # Save the .pb model file
            output_graph_def = tf.graph_util.convert_variables_to_constants(sess, sess.graph_def,
                                                                            output_node_names.split("|"))
            tf.train.write_graph(output_graph_def, 'graph', 'graph-cnn-{0}.pb'.format(MODEL), as_text=False)

            # Generate batches for one epoch
            batches = dh.batch_iter(list(zip(x_test, y_test, y_test_labels)), FLAGS.batch_size, 1, shuffle=False)

            # Collect the predictions here
            all_labels = []
            all_predicted_labels = []
            all_predicted_values = []

            # Calculate the metric
            test_counter, test_loss, test_rec, test_pre, test_F = 0, 0.0, 0.0, 0.0, 0.0

            for batch_test in batches:
                x_batch_test, y_batch_test, y_batch_test_labels = zip(*batch_test)
                feed_dict = {
                    input_x: x_batch_test,
                    input_y: y_batch_test,
                    dropout_keep_prob: 1.0,
                    is_training: False
                }
                batch_scores, cur_loss = sess.run([scores, loss], feed_dict)

                # Predict by threshold
                predicted_labels_threshold, predicted_values_threshold = \
                    dh.get_label_using_scores_by_threshold(scores=batch_scores, threshold=FLAGS.threshold)

                cur_rec, cur_pre, cur_F = 0.0, 0.0, 0.0

                for index, predicted_label_threshold in enumerate(predicted_labels_threshold):
                    rec_inc, pre_inc = dh.cal_metric(predicted_label_threshold, y_batch_test[index])
                    cur_rec, cur_pre = cur_rec + rec_inc, cur_pre + pre_inc

                cur_rec = cur_rec / len(y_batch_test)
                cur_pre = cur_pre / len(y_batch_test)

                test_rec, test_pre = test_rec + cur_rec, test_pre + cur_pre

                # Add results to collection
                for item in y_batch_test_labels:
                    all_labels.append(item)
                for item in predicted_labels_threshold:
                    all_predicted_labels.append(item)
                for item in predicted_values_threshold:
                    all_predicted_values.append(item)

                test_loss = test_loss + cur_loss
                test_counter = test_counter + 1

            test_loss = float(test_loss / test_counter)
            test_rec = float(test_rec / test_counter)
            test_pre = float(test_pre / test_counter)
            test_F = dh.cal_F(test_rec, test_pre)

            logger.info("All Test Dataset: Loss {0:g}".format(test_loss))

            # Predict by threshold
            logger.info("︎Predict by threshold: Recall {0:g}, Precision {1:g}, F {2:g}"
                        .format(test_rec, test_pre, test_F))
            # Save the prediction result
            if not os.path.exists(SAVE_DIR):
                os.makedirs(SAVE_DIR)
            dh.create_prediction_file(output_file=SAVE_DIR + '/predictions.json', data_id=test_data.testid,
                                      all_labels=all_labels, all_predict_labels=all_predicted_labels,
                                      all_predict_values=all_predicted_values)

    logger.info("Done.")


if __name__ == '__main__':
    test_cnn()
