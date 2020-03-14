import boto3
from datetime import datetime, timedelta
import math
import time
import logging
#import app.config
# from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import *

# import pymysql



ami_id = 'ami-06981bc111789bad7'
zone = 'us-east-1a'
key_name = 'ece1779_a1'
security_group = ['sg-041902e4d97796241']
subnet_id = 'subnet-3d00e762'
ec2_name = 'ece1779_a2_new'
targetgroup_ARN = "arn:aws:elasticloadbalancing:us-east-1:027297473206:targetgroup/ece1779tg/41ab005ed602520b"
rolename = 'a2'

#config = app.config.Config
engine = create_engine(
    'mysql+pymysql://ece1779db:ece1779db@ece1779db.cj2g85prhcmw.us-east-1.rds.amazonaws.com/1779dbA2')


class Autoscaling_Services:
    EC2 = boto3.client('ec2')
    ELB = boto3.client('elbv2')
    S3 = boto3.client('s3')
    cloud_watch = boto3.client("cloudwatch")


    def get_stopped_instances(self):
        ec2_filter = [{'Name': 'tag:Name', 'Values': [ec2_name]},
                      {'Name': 'instance-state-name', 'Values': ['stopped']}]
        return self.EC2.describe_instances(Filters=ec2_filter)

    def start_instance(self, instance_id):
        self.EC2.start_instances(InstanceIds=[instance_id])

    # Launches instance using an AMI .
    def create_new_instance(self):
        response = self.EC2.run_instances(
            ImageId=ami_id,
            Placement={'AvailabilityZone': zone},
            InstanceType='t2.small',
            IamInstanceProfile={
                # 'Arn':targetgroup_ARN
                'Name': rolename
            },
            MinCount=1,
            MaxCount=1,
            # Userdata=config.userdata,
            Monitoring={'Enabled': True},
            KeyName=key_name,
            SubnetId=subnet_id,
            SecurityGroupIds=security_group,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': ec2_name
                        },
                    ]
                },
            ],
        )
        for instance in response['Instances']:
            print(instance['InstanceId'] + " created!")
        return response['Instances'][0]['InstanceId']

    def grow_one_worker(self):
        #target_instance_id = self.get_available_target()
        error = False
        stopped_instances = self.get_stopped_instances()['Reservations']
        if stopped_instances:
            new_instance_id = stopped_instances[0]['Instances'][0]['InstanceId']
            self.start_instance(new_instance_id)
        else:
            new_instance_id = self.create_new_instance()
        status = self.EC2.describe_instance_status(InstanceIds=[new_instance_id])
        while len(status['InstanceStatuses']) < 1:
            time.sleep(1)
            status = self.EC2.describe_instance_status(InstanceIds=[new_instance_id])
        while status['InstanceStatuses'][0]['InstanceState']['Name'] != 'running':
            time.sleep(1)
            status = self.EC2.describe_instance_status(InstanceIds=[new_instance_id])
        self.target_register(new_instance_id)
        return [error, '']

    def get_available_target(self):
        available_instances_id = []
        target_group = self.ELB.describe_target_health(TargetGroupArn=targetgroup_ARN)
        target_group_health_desc = target_group['TargetHealthDescriptions']
        if target_group_health_desc:
            for target in target_group_health_desc:
                if target['TargetHealth']['State'] != 'draining':
                    available_instances_id.append(target['Target']['Id'])
        return available_instances_id

    def auto_scaling_policy(self):
        db = engine.connect()
        metadata = MetaData(db)
        table = Table('autoscaling', metadata, autoload=True)
        s = select([table]).where(table.c.id == 1)
        cur = db.execute(s)
        item = cur.fetchone()
        parameters = item
        if item is None:
            i = table.insert()
            db.execute(i, threshold_growing="80", threshold_shrinking="20", ratio_growing="2", ratio_shrinking="2")
            db.close()
        else:
            parameters = (1, 80, 20, 2.00, 2.00)
        return parameters

    def get_running_instances(self):
        ec2_filter = [{'Name': 'tag:Name', 'Values': [ec2_name]},
                      {'Name': 'instance-state-name', 'Values': ['running']}]
        return self.EC2.describe_instances(Filters=ec2_filter)

    def get_using_target(self):
        available_instances_id = []
        target_group = self.ELB.describe_target_health(TargetGroupArn=targetgroup_ARN)
        if target_group['TargetHealthDescriptions']:
            for target in target_group['TargetHealthDescriptions']:
                if target['TargetHealth']['State'] != 'unhealthy':
                    available_instances_id.append(target['Target']['Id'])
        return available_instances_id

    def get_cpu_utility(self):
        valid_targets = self.ELB.describe_target_health(TargetGroupArn=targetgroup_ARN)[
            "TargetHealthDescriptions"]
        cpu_sum = 0
        cpu_count = 0
        lasttime = 0
        for target in valid_targets:
            instance_id = target['Target']['Id']
            response = self.cloud_watch.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[
                    {
                        'Name': 'InstanceId',
                        'Value': instance_id,
                    }
                ],
                Statistics=['Average'],
                StartTime=datetime.utcnow() - timedelta(seconds=2 * 60),
                EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
                Period=60,  # Data points with a period of 60 seconds (1-minute) are available for 15 days.
            )
            try:
                lasttime = response["Datapoints"][0]["Timestamp"]
                cpu_sum += response["Datapoints"][0]["Average"]
                cpu_count = cpu_count + 1
            except IndexError:
                pass

        cpu_sum_avg = cpu_sum / cpu_count if cpu_count else -1

        return cpu_count, cpu_sum_avg, lasttime

    def target_register(self, instance_id):
        self.ELB.register_targets(
            TargetGroupArn=targetgroup_ARN,
            Targets=[{'Id': instance_id, 'Port': 5000}]
        )

    def target_derigister(self, instance_id):
        self.ELB.deregister_targets(
            TargetGroupArn=targetgroup_ARN,
            Targets=[{'Id': instance_id, 'Port': 5000}]
        )

    def stop_instance(self, instance_id):
        self.EC2.stop_instances(InstanceIds=[instance_id], Hibernate=False, Force=False)

    def auto_scaling(self):
        logging.warning('-----------auto_scaling------------------------------------')
        policy = self.auto_scaling_policy()
        threshold_growing = policy[1]
        threshold_shrinking = policy[2]
        ratio_growing = policy[3]
        ratio_shrinking = policy[4]
        current_time = datetime.now()
        instance_amount, cpu_utils, lasttime = self.get_cpu_utility()
        logging.warning("Time is {}".format(lasttime))
        logging.warning("instance amount is {}".format(instance_amount))
        logging.warning("cpu_utils is {}".format(cpu_utils))
        logging.warning(
            "threshold_growing:{0}, shrinking:{1}, ratio growing:{2}, ratio shrinking:{3}".format(threshold_growing,
                                                                                                  threshold_shrinking,
                                                                                                  ratio_growing,
                                                                                                  ratio_shrinking))
        if instance_amount == 0:
            logging.warning('{} no workers in the pool'.format(current_time))
            running_instances=self.get_running_instances()['Reservations']
            if running_instances:
                self.grow_one_worker()
                logging.warning('{} Create a worker if there is no worker in the pool now'.format(current_time))

        if cpu_utils > threshold_growing:
            response = self.grow_worker_by_ratio(threshold_growing, ratio_growing)
            logging.warning('{} grow workers: {}'.format(current_time, response))
        elif cpu_utils < threshold_shrinking:
            response = self.shrink_worker_by_ratio(threshold_shrinking, ratio_shrinking)
            logging.warning('{} shrink workers: {}'.format(current_time, response))
        else:
            logging.warning('{} nothing to change'.format(current_time))

        logging.warning('-----------------------------------------------------------')


    def grow_worker_by_ratio(self, threshold_growing, ratio_growing):
        instance_amount, current_cpu_util, lasttime = self.get_cpu_utility()
        instance_list = []
        # worker_management = EC2_Services()
        if current_cpu_util > threshold_growing:
            if instance_amount < 10:
                instance_needs_to_start = math.floor(instance_amount * ratio_growing - instance_amount)
                temp_num_of_instances = instance_amount + instance_needs_to_start
                if (temp_num_of_instances > 10):
                    instance_needs_to_start = instance_needs_to_start - (temp_num_of_instances - 10)

                print('instance_needs_to_start:', instance_needs_to_start)
                error = False
                stopped_instances = self.get_stopped_instances()['Reservations']
                if stopped_instances:
                    if len(stopped_instances) < instance_needs_to_start:
                        for i in range(len(stopped_instances)):  # restart all stopped instances
                            # need to check stopped_instances type! original:new_instance_id = stopped_instances[0]['Instances'][0]['InstanceId']
                            new_instance_id = stopped_instances[0]['Instances'][i]['InstanceId']
                            instance_list.append(new_instance_id)
                            self.start_instance(new_instance_id)
                            instance_needs_to_start = instance_needs_to_start - len(stopped_instances)
                    else:
                        for i in range(instance_needs_to_start):
                            new_instance_id = stopped_instances[0]['Instances'][i]['InstanceId']
                            instance_list.append(new_instance_id)
                            self.start_instance(new_instance_id)
                            instance_needs_to_start = 0
                            # return [error, ''] # not sure, need to check this return

                # create new instances
                if instance_needs_to_start > 0:
                    for i in range(instance_needs_to_start):
                        new_instance_id = self.create_new_instance()
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
            self.target_register(temp_id)

        return instance_list

    def shrink_worker_by_ratio(self, threshold_shrinking, ratio_shrinking):
        instance_amount, current_cpu_util, lasttime = self.get_cpu_utility()
        current_amount = instance_amount
        # worker_management = EC2_Services()
        target_instance_id = self.get_available_target()
        running_instances = target_instance_id
        instance_list = []
        if current_cpu_util < threshold_shrinking:
            if instance_amount > 1:
                instance_needs_to_stop = math.ceil(instance_amount / ratio_shrinking)
                for i in range(instance_needs_to_stop):
                    if (current_amount < 2):
                        break
                    if (running_instances[i] != 'i-0350edfa61b87909e'):  # do not stop instance for a2
                        self.target_derigister(running_instances[i])
                        self.stop_instance(running_instances[i])
                        current_amount = current_amount - 1
                        instance_list.append(running_instances[i])

        return instance_list


autoSacler = Autoscaling_Services()
autoSacler.auto_scaling()
