from flask import render_template, redirect, url_for, request
from app import webapp
from datetime import datetime, timedelta
from operator import itemgetter
from app.Services.EC2 import *
from app.Services.Autoscaling import Autoscaling_Services

@webapp.route('/ec2_examples', methods=['GET'])
# Display an HTML list of all ec2 instances
def ec2_list():
    # create connection to ec2
    ec2 = boto3.resource('ec2')

    #    instances = ec2.instances.filter(
    #        Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])

    instances = ec2.instances.all()

    return render_template("ec2_examples/list.html", title="EC2 Instances", instances=instances)


@webapp.route('/ec2_examples/<id>', methods=['GET'])
# Display details about a specific instance.
def ec2_view(id):
    ec2 = boto3.resource('ec2')

    instance = ec2.Instance(id)

    client = boto3.client('cloudwatch')

    metric_name = 'CPUUtilization'

    ##    CPUUtilization, NetworkIn, NetworkOut, NetworkPacketsIn,
    #    NetworkPacketsOut, DiskWriteBytes, DiskReadBytes, DiskWriteOps,
    #    DiskReadOps, CPUCreditBalance, CPUCreditUsage, StatusCheckFailed,
    #    StatusCheckFailed_Instance, StatusCheckFailed_System

    namespace = 'AWS/EC2'
    statistic = 'Average'  # could be Sum,Maximum,Minimum,SampleCount,Average

    cpu = client.get_metric_statistics(
        Period=1 * 60,
        StartTime=datetime.utcnow() - timedelta(seconds=60 * 60),
        EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
        MetricName=metric_name,
        Namespace=namespace,  # Unit='Percent',
        Statistics=[statistic],
        Dimensions=[{'Name': 'InstanceId', 'Value': id}]
    )

    cpu_stats = []

    for point in cpu['Datapoints']:
        hour = point['Timestamp'].hour
        minute = point['Timestamp'].minute
        time = hour + minute / 60
        cpu_stats.append([time, point['Average']])

    cpu_stats = sorted(cpu_stats, key=itemgetter(0))

    statistic = 'Sum'  # could be Sum,Maximum,Minimum,SampleCount,Average

    network_in = client.get_metric_statistics(
        Period=1 * 60,
        StartTime=datetime.utcnow() - timedelta(seconds=60 * 60),
        EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
        MetricName='NetworkIn',
        Namespace=namespace,  # Unit='Percent',
        Statistics=[statistic],
        Dimensions=[{'Name': 'InstanceId', 'Value': id}]
    )

    net_in_stats = []

    for point in network_in['Datapoints']:
        hour = point['Timestamp'].hour
        minute = point['Timestamp'].minute
        time = hour + minute / 60
        net_in_stats.append([time, point['Sum']])

    net_in_stats = sorted(net_in_stats, key=itemgetter(0))

    network_out = client.get_metric_statistics(
        Period=5 * 60,
        StartTime=datetime.utcnow() - timedelta(seconds=60 * 60),
        EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
        MetricName='NetworkOut',
        Namespace=namespace,  # Unit='Percent',
        Statistics=[statistic],
        Dimensions=[{'Name': 'InstanceId', 'Value': id}]
    )

    net_out_stats = []

    for point in network_out['Datapoints']:
        hour = point['Timestamp'].hour
        minute = point['Timestamp'].minute
        time = hour + minute / 60
        net_out_stats.append([time, point['Sum']])

        net_out_stats = sorted(net_out_stats, key=itemgetter(0))

    return render_template("ec2_examples/view.html", title="Instance Info",
                           instance=instance,
                           cpu_stats=cpu_stats,
                           net_in_stats=net_in_stats,
                           net_out_stats=net_out_stats)


@webapp.route('/ec2_examples/grow', methods=['POST'])
# Start a new EC2 instance
# Create a EC2 instance
def worker_grow():
    worker_management = EC2_Services()
    [error, message] = worker_management.grow_one_worker()
    if error:
        return redirect(url_for('ec2_list'))
    else:
        return redirect(url_for('ec2_list'))


@webapp.route('/ec2_examples/shrink', methods=['POST'])
def worker_shrink():
    worker_management = EC2_Services()
    [error, message] = worker_management.shrink_one_worker()
    if error:
        return redirect(url_for('ec2_list'))
    else:
        return redirect(url_for('ec2_list'))


@webapp.route('/ec2_examples/delete/<id>', methods=['POST'])
# Terminate a EC2 instance
def ec2_destroy(id):
    # create connection to ec2
    ec2 = boto3.resource('ec2')
    ec2.instances.filter(InstanceIds=[id]).terminate()

    return redirect(url_for('ec2_list'))

# Activate the autoscaling services(temporarily)
@webapp.route('/ec2_examples/autoscaling', methods=['POST'])
def autoscaling():
    worker_management = Autoscaling_Services()
    worker_management.auto_scaling()
    return redirect(url_for('ec2_list'))

@webapp.route('/s3_examples',methods=['GET'])
# Display an HTML list of all s3 buckets.
def s3_list():
    # Let's use Amazon S3
    s3 = boto3.resource('s3')

    # Print out bucket names
    buckets = s3.buckets.all()

    for b in buckets:
        name = b.name

    buckets = s3.buckets.all()

    return render_template("s3_examples/list.html",title="s3 Instances",buckets=buckets)


@webapp.route('/s3_examples/<id>',methods=['GET'])
#Display details about a specific bucket.
def s3_view(id):
    s3 = boto3.resource('s3')

    bucket = s3.Bucket(id)

    for key in bucket.objects.all():
        k = key

    keys =  bucket.objects.all()


    return render_template("s3_examples/view.html",title="S3 Bucket Contents",id=id,keys=keys)


@webapp.route('/s3_examples/upload/<id>',methods=['POST'])
#Upload a new file to an existing bucket
def s3_upload(id):
    # check if the post request has the file part
    if 'new_file' not in request.files:
        return redirect(url_for('s3_view',id=id))

    new_file = request.files['new_file']

    # if user does not select file, browser also
    # submit a empty part without filename
    if new_file.filename == '':
        return redirect(url_for('s3_view', id=id))

    s3 = boto3.client('s3')

    s3.upload_fileobj(new_file, id, new_file.filename)

    return redirect(url_for('s3_view', id=id))
