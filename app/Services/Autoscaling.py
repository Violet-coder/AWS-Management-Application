from app.Services.EC2 import *
import boto3
from datetime import datetime, timedelta
import math
import time
import logging
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import *
import pymysql
import json

config = app.config.Config
engine = create_engine('mysql+pymysql://ece1779db:ece1779db@ece1779db.cj2g85prhcmw.us-east-1.rds.amazonaws.com/1779dbA2')


class Autoscaling_Services:
    EC2 = boto3.client('ec2')
    ELB = boto3.client('elbv2')
    S3 = boto3.client('s3')
    cloud_watch = boto3.client("cloudwatch")

    def auto_scaling_policy(self):
        ''''
        db = engine.connect()
        metadata = MetaData(db)
        table = Table('autoscaling', metadata, autoload=True)
        s = select([table]).where(table.c.id == 1)
        cur = db.execute(s)
        item = cur.fetchone()
        parameters = item
        if item is None:
            i = table.insert()
            db.execute(i,threshold_growing="80", threshold_shrinking = "20", ratio_growing = "2", ratio_shrinking = "2" )
            db.close()
            #parameters = (80, 20, 2.00, 2.00)
        else:
        '''
        parameters = (1, 80, 20, 2.00, 2.00)
        return parameters

    def get_using_target(self):
        available_instances_id = []
        target_group = self.ELB.describe_target_health(TargetGroupArn=config.targetgroup_ARN)
        if target_group['TargetHealthDescriptions']:
            for target in target_group['TargetHealthDescriptions']:
                if target['TargetHealth']['State'] != 'unhealthy':
                    available_instances_id.append(target['Target']['Id'])
        return available_instances_id


    def get_cpu_utility(self):
        #valid_targets = self.ELB.describe_target_health(TargetGroupArn=config.targetgroup_ARN)["TargetHealthDescriptions"]
        valid_targets_id = self.get_using_target()
        #print(valid_targets_id)
        cpu_sum = 0
        cpu_count = 0
        #id = []
        lasttime = 0
        #valid_targets = self.get_using_target()
        #l = len(valid_instances)
        for target in valid_targets_id:
            instance_id = target
            #instance_id = target['Target']['Id']
            #print(instance_id)
            #id.append(instance_id)
            response = self.cloud_watch.get_metric_statistics(
                Namespace = "AWS/EC2",
                MetricName = "CPUUtilization",
                Dimensions = [
                {
                    'Name': 'InstanceId',
                    'Value': instance_id,
                }
                ],
                Statistics=['Average'],
                StartTime=datetime.utcnow() - timedelta(seconds=2 * 60),
                EndTime=datetime.utcnow()- timedelta(seconds=0 * 60),
                Period= 60,  #Data points with a period of 60 seconds (1-minute) are available for 15 days.
            )
            #print(response)
            try:
                lasttime = response["Datapoints"][0]["Timestamp"]
                cpu_sum += response["Datapoints"][0]["Average"]
                cpu_count = cpu_count + 1
            except IndexError:
                pass

        cpu_sum_avg = cpu_sum / cpu_count if cpu_count else -1

        return cpu_count, cpu_sum_avg, lasttime

    def auto_scaling(self):
        policy = self.auto_scaling_policy()
        threshold_growing = policy[1]
        threshold_shrinking = policy[2]
        ratio_growing = policy[3]
        ratio_shrinking = policy[4]
        print(threshold_shrinking)
        current_time = datetime.now()
        instance_amount, cpu_utils, lasttime = self.get_cpu_utility()


        #logging.INFO("=================auto_scaling=================")
        #logging.INFO("Time is {}".format(lasttime))
        #logging.INFO("cpu_utils")
        print("instance_amount",instance_amount)
        print("cpu_utils",cpu_utils)
        #print("lasttime", lasttime)
        # if there is no valid instances, then do nothing.
        if instance_amount == -1:
            pass
        #logging.warning('{} no workers in the pool'.format(current_time))
        # cpu_grow, cpu_shrink, ratio_expand, ratio_shrink
        if cpu_utils > threshold_growing:
            response = self.grow_worker_by_ratio(threshold_growing,ratio_growing)
            #logging.warning('{} grow workers: {}'.format(current_time, response))
            print('in grow function')
            print(response)
        elif cpu_utils < threshold_shrinking:
            print('111112')
            response = self.shrink_worker_by_ratio(threshold_shrinking,ratio_shrinking)
            print('in shrink function')
            print(response)
            #logging.warning('{} shrink workers: {}'.format(current_time, response))
        else:
            logging.warning('{} nothing to change'.format(current_time))


    def grow_worker_by_ratio(self, threshold_growing, ratio_growing):
        instance_amount, current_cpu_util, lasttime = self.get_cpu_utility()

        instance_list = []
        worker_management = EC2_Services()
        if current_cpu_util > threshold_growing:
            if instance_amount < 10:
                instance_needs_to_start = math.floor(instance_amount * ratio_growing - instance_amount)
                temp_num_of_instances=instance_amount+ instance_needs_to_start
                if (temp_num_of_instances > 10):
                    instance_needs_to_start=instance_needs_to_start-(temp_num_of_instances - 10)

                print('instance_needs_to_start:',instance_needs_to_start)
                error = False
                stopped_instances = worker_management.get_stopped_instances()['Reservations']
                if stopped_instances:
                    if len(stopped_instances) < instance_needs_to_start :
                        for i in range(len(stopped_instances)):  # restart all stopped instances
                            # need to check stopped_instances type! original:new_instance_id = stopped_instances[0]['Instances'][0]['InstanceId']
                            new_instance_id = stopped_instances[0]['Instances'][i]['InstanceId']
                            instance_list.append(new_instance_id)
                            worker_management.start_instance(new_instance_id)
                            instance_needs_to_start = instance_needs_to_start - len(stopped_instances)
                    else:
                        for i in range(instance_needs_to_start):
                            new_instance_id = stopped_instances[0]['Instances'][i]['InstanceId']
                            instance_list.append(new_instance_id)
                            worker_management.start_instance(new_instance_id)
                            instance_needs_to_start = 0
                            # return [error, ''] # not sure, need to check this return

                # create new instances
                if instance_needs_to_start > 0:
                    for i in range(instance_needs_to_start):
                        new_instance_id = worker_management.create_new_instance()
                        instance_list.append(new_instance_id)



        all_run = False
        while (all_run == False):
            for i in range(len(instance_list)):
                temp_id = instance_list[i]
                status = self.EC2.describe_instance_status(InstanceIds=[temp_id])

                while len(status['InstanceStatuses']) < 1:
                    time.sleep(1)
                    status = self.EC2.describe_instance_status(InstanceIds=[temp_id])

                while status['InstanceStatuses'][0]['InstanceState']['Name'] != 'running':
                    time.sleep(1)
                    status = self.EC2.describe_instance_status(InstanceIds=[temp_id])
            all_run = True

        for i in range(len(instance_list)):
            temp_id = instance_list[i]
            worker_management.target_register(temp_id)

        return instance_list

    def shrink_worker_by_ratio(self, threshold_shrinking, ratio_shrinking):
        instance_amount, current_cpu_util, lasttime = self.get_cpu_utility()
        current_amount = instance_amount
        worker_management = EC2_Services()
        target_instance_id = worker_management.get_available_target()
        running_instances = target_instance_id
        print(running_instances)
        instance_list=[]
        if current_cpu_util < threshold_shrinking:
            if instance_amount > 1:
                instance_needs_to_stop = math.floor(instance_amount / ratio_shrinking)

                for i in range(instance_needs_to_stop):
                    if (current_amount < 2):
                        break
                    worker_management.target_derigister(running_instances[i])
                    worker_management.stop_instance(running_instances[i])
                    current_amount = current_amount - 1
                    instance_list.append(running_instances[i])

        return  instance_list


