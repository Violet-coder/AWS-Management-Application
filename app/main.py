from flask import render_template, redirect, url_for, request, g
from app import webapp
from app.Services.EC2 import *


@webapp.route('/index',methods=['GET'])
@webapp.route('/main',methods=['GET'])
# Display an HTML page with links
def main():
    return render_template("main_page.html",title="Landing Page")
