import time
import boto3
import app.config
from sqlalchemy import *



config = app.config.Config
engine = create_engine('mysql+pymysql://ece1779db:ece1779db@ece1779db.cj2g85prhcmw.us-east-1.rds.amazonaws.com/1779db')


class EC2_Services:
    EC2 = boto3.client('ec2')
    ELB = boto3.client('elbv2')
    S3 = boto3.client('s3')


    def worker_list_chart(self):
        running_instances = self.get_running_instances()
        stopped_instances = self.get_stopped_instances()['Reservations']
        current_instances = len(running_instances) + len(stopped_instances)
        self.workers_list.append(current_instances)

    def

    def target_register(self, instance_id):
        self.ELB.register_targets(
            TargetGroupArn=config.targetgroup_ARN,
            Targets=[{'Id': instance_id, 'Port': 5000}]
        )

    def target_derigister(self, instance_id):
        self.ELB.deregister_targets(
            TargetGroupArn=config.targetgroup_ARN,
            Targets=[{'Id': instance_id, 'Port': 5000}]
        )

    def get_available_target(self):
        available_instances_id = []
        target_group = self.ELB.describe_target_health(TargetGroupArn=config.targetgroup_ARN)
        target_group_health_desc = target_group['TargetHealthDescriptions']
        if target_group_health_desc:
            for target in target_group_health_desc:
                if target['TargetHealth']['State'] != 'draining':
                    available_instances_id.append(target['Target']['Id'])
        return available_instances_id

    # Launches instance using an AMI .
    def create_new_instance(self):
        response = self.EC2.run_instances(
            ImageId=config.ami_id,
            Placement={'AvailabilityZone': config.zone},
            InstanceType='t2.small',
            MinCount=1,
            MaxCount=1,
            #Userdata=config.userdata,
            Monitoring={'Enabled': True},
            KeyName=config.key_name,
            SubnetId=config.subnet_id,
            SecurityGroupIds=config.security_group,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': config.ec2_name
                        },
                    ]
                },
            ],
        )
        for instance in response['Instances']:
            print(instance['InstanceId'] + " created!")
        return response['Instances'][0]['InstanceId']

    def get_stopped_instances(self):
        ec2_filter = [{'Name': 'tag:Name', 'Values': [config.ec2_name]},
                      {'Name': 'instance-state-name', 'Values': ['stopped']}]
        return self.EC2.describe_instances(Filters=ec2_filter)

    def get_running_instances(self):
        ec2_filter = [{'Name': 'tag:Name', 'Values': [config.ec2_name]},
                      {'Name': 'instance-state-name', 'Values': ['running']}]
        return self.EC2.describe_instances(Filters=ec2_filter)

    def grow_one_worker(self):
        target_instance_id = self.get_available_target()
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

    def shrink_one_worker(self):
        target_instance_id = self.get_available_target()
        running_instances = target_instance_id
        error = False
        if len(running_instances) < 1:
            error = True
            return [error, 'No more worker to shrink!']
        else:
            self.target_derigister(running_instances[0])
            self.stop_instance(running_instances[0])
            return [error, '']

    def start_instance(self, instance_id):
        self.EC2.start_instances(InstanceIds=[instance_id])

    def stop_instance(self, instance_id):
        self.EC2.stop_instances(InstanceIds=[instance_id], Hibernate=False, Force=False)

    def terminate_instance(self, instance_id):
        self.EC2.terminate_instances(InstanceIds=[instance_id], Hibernate=False, Force=False)

    def delete_app_data_rds(self):
        db = engine.connect()
        metadata = MetaData(db)
        #Table users
        table = Table('users', metadata, autoload=True)
        d = table.delete()
        db.execute(d)
        #Table user_phtoto
        table = Table('user_photo', metadata, autoload=True)
        d = table.delete()
        db.execute(d)
        db.close()





