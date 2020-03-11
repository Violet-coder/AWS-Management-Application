import time
import boto3
import app.config


class EC2_Services:
    EC2 = boto3.client('ec2')
    ELB = boto3.client('elbv2')
    S3 = boto3.client('s3')

    def target_register(self, instance_id):
        self.ELB.register_targets(
            TargetGroupArn=app.config.Config.targetgroup_ARN,
            Targets=[{'Id': instance_id,'Port': 5000}]
        )
    def target_derigister(self, instance_id):
        self.ELB.deregister_targets(
            TargetGroupArn=app.config.Config.targetgroup_ARN,
            Targets=[{'Id': instance_id, 'Port': 5000}]
        )

    def get_available_target(self):
        available_instances_id = []
        target_group = self.ELB.describe_target_health(TargetGroupArn=app.config.Config.targetgroup_ARN)
        if target_group['TargetHealthDescriptions']:
            for target in target_group['TargetHealthDescriptions']:
                if target['TargetHealth']['State'] != 'draining':
                    available_instances_id.append(target['Target']['Id'])
        return available_instances_id


    def create_new_instance(self):
        response = self.EC2.run_instances(
            ImageId=app.config.Config.ami_id,
            Placement={'AvailabilityZone': app.config.Config.zone},
            InstanceType='t2.small',
            MinCount=1,
            MaxCount=1,
            Monitoring = {'Enabled':True},
            KeyName=app.config.Config.key_name,
            SubnetId=app.config.Config.subnet_id,
            SecurityGroupIds=app.config.Config.security_group,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': app.config.Config.ec2_name
                        },
                    ]
                },
            ],
        )
        for instance in response['Instances']:
            print(instance['InstanceId'] + " created!")
        return response['Instances'][0]['InstanceId']

    def get_stopped_instances(self):
        ec2_filter = [{'Name': 'tag:Name', 'Values': [app.config.Config.ec2_name]},
                      {'Name': 'instance-state-name', 'Values': ['stopped']}]
        return self.EC2.describe_instances(Filters=ec2_filter)

    def get_running_instances(self):
        ec2_filter = [{'Name': 'tag:Name', 'Values': [app.config.Config.ec2_name]},
                      {'Name': 'instance-state-name', 'Values': ['running']}]
        return self.EC2.describe_instances(Filters=ec2_filter)

    def grow_one_worker(self):
        target_instance_id = self.get_available_target()
        error = False
        stopped_instances = self.get_stopped_instances()['Reservations']
        if stopped_instances:
            new_instance_id = stopped_instances[0]['Instances'][0]['InstanceId']
            self.start_instance(new_instance_id)
        else:  # create a new instance
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
