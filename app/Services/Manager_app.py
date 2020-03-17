from flask import render_template, redirect, url_for, request, flash
from app import webapp
from datetime import datetime, timedelta
from operator import itemgetter
from app.Services.EC2 import *
from app.Services.Autoscaling import Autoscaling_Services
from sqlalchemy import *
from app.Services.model import Autoscaling

engine = create_engine('mysql+pymysql://ece1779db:ece1779db@ece1779db.cj2g85prhcmw.us-east-1.rds.amazonaws.com/1779dbA2')


@webapp.route('/ec2_examples/stop_manager', methods=['GET', 'POST'])
def stop_manager():
    worker_management = EC2_Services()
    worker_management.stop_manager()
    return render_template("main_page.html")

@webapp.route('/', methods=['GET', 'POST'])
def mainpage():
    return render_template("main_page.html")

@webapp.route('/ec2_examples', methods=['GET'])
# Display an HTML list of all ec2 instances
def ec2_list():
    # create connection to ec2
    ec2 = boto3.resource('ec2')
    instances = ec2.instances.all()
    return render_template("EC2_example.html", title="EC2 Instances", instances=instances)


@webapp.route('/ec2_examples/<id>', methods=['GET'])
# Display the CPU utilization and http request about a specific instance.
def ec2_view(id):
    ec2 = boto3.resource('ec2')
    instance = ec2.Instance(id)
    client = boto3.client('cloudwatch')
    metric_name = 'CPUUtilization'
    namespace = 'AWS/EC2'
    statistic = 'Average'  # could be Sum,Maximum,Minimum,SampleCount,Average

    cpu = client.get_metric_statistics(
        Period=1 * 60,
        StartTime=datetime.utcnow() - timedelta(seconds=30 * 60),
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

    graph_address = 'https://users12.s3.amazonaws.com/http/' + str(id) + '.jpg'

    return render_template("EC2_view.html", title="Instance Info", instance=instance, cpu_stats=cpu_stats,graph_adress=graph_address)

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

@webapp.route('/ec2_examples/delete_app_data', methods=['POST'])
def delete_app_data():
    worker_management = EC2_Services( )
    worker_management.delete_app_data_rds()
    return redirect(url_for('ec2_list'))

@webapp.route('/ec2_examples/numberofworkers', methods=['GET','POST'])
def get_chart_numofworkers():
    cloud_watch = boto3.client("cloudwatch")
    num = cloud_watch.get_metric_statistics(
        Period=1 * 60,
        StartTime=datetime.utcnow() - timedelta(seconds=30 * 60),
        EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
        MetricName='HealthyHostCount',
        Namespace='AWS/ApplicationELB',  # Unit='Percent',
        Statistics=['Average'],
        Dimensions=[{'Name': 'TargetGroup', 'Value':'targetgroup/ece1779tg/41ab005ed602520b'},
                    {'Name':'LoadBalancer','Value':'app/loadbalancer1/05af72b04f53de13'}
                    ]
    )

    worker_num=[]

    for point in num['Datapoints']:
        hour = point['Timestamp'].hour
        minute = point['Timestamp'].minute
        time = hour + minute / 60
        worker_num.append([time, point['Average']])
    worker_num = sorted(worker_num, key=itemgetter(0))


    return render_template("numofworkers.html", title="Number of Workers", worker_num = worker_num)


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


    return render_template("S3_example.html",title="s3 Instances",buckets=buckets)

@webapp.route('/s3_examples/delete')
def delete_s3():
    s3 = boto3.resource('s3')
    worker_management=EC2_Services()
    my_bucket = s3.Bucket('users12')
    my_bucket.objects.filter(Prefix='user_photo').delete()
    my_bucket.objects.filter(Prefix='http').delete()
    worker_management.delete_app_data_rds()
    flash('successfully!')
    return render_template("main_page.html")



@webapp.route('/autoscaling/',methods=['GET', 'POST'])
def get_autoscaling_policy_from_users():
    if request.method == "POST":
        autoscaling=Autoscaling()
        autoscaling.threshold_growing = request.form['threshold_growing']
        autoscaling.threshold_shrinking = request.form['threshold_shrinking']
        autoscaling.ratio_growing = request.form['ratio_growing']
        autoscaling.ratio_shrinking = request.form['ratio_shrinking']
        update_autoscaling_policy_to_db(autoscaling)
    return render_template('auto_scaling.html')

def update_autoscaling_policy_to_db(autoscaling):
    db = engine.connect()
    metadata = MetaData(db)
    table = Table('autoscaling', metadata, autoload=True)
    u = table.update().values(threshold_growing=autoscaling.threshold_growing,threshold_shrinking=autoscaling.threshold_shrinking,
                              ratio_growing=autoscaling.ratio_growing,ratio_shrinking=autoscaling.ratio_shrinking).where(table.c.id ==1)
    db.execute(u)
    db.close()
