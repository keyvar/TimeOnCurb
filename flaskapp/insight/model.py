import pickle
import googlemaps
from datetime import datetime
import time
import pandas as pd 
import numpy as np
import warnings
warnings.filterwarnings('ignore')
import matplotlib.pyplot as plt
import seaborn as sns
import scipy.io as sio
import scipy as sp
import folium
from math import radians, cos, sin, asin, sqrt, atan, atan2, pi

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
from sklearn.ensemble import RandomForestRegressor
import xgboost
import logging
import re 
import math
import json
import requests


fxmlUrl = ""
flight_aware_username = ""
flight_aware_api_key = ''

gmaps_api_key = ''

project_directory = r'insight/'
resources_directory = r'insight/resources/'

# The following coeficients are used to estimate the number of passengers arriving in a terminal.
monthly_passenger_coef = {
'April':        1.187390,
'August':       1.236191,
'December':     1.000000,
'February':     1.055634,
'January':      1.138858,
'July':         1.236023,
'June':         1.180202,
'March':        1.034820,
'May':          1.142991,
'November':     1.029827,
'October':      1.074053,
'September':    1.125654}

terminal_passenger_flow = {
't1': 125.583717,
't2': 7.644068,
't3': 115.390465,
't4' : 151.285584,
't5': 223.693502
}


def roundup(x, base):
	# rounds the number to nearest multiplicity of base.
	# for example, roundup(5.2, 5) = 10
    return int(math.ceil(x / base)) * base

def binize_hour(date):
	# puts a given time in 1 hour buckets.
	# for example "11:22:23" = "1100 - 1200", "23:18:43" = "2300 - 0000"
	hour = date.hour
	arrival_hour = ''
	if hour < 9:
		arrival_hour = '0' + str(hour) + '00 - 0' + str(hour + 1) + '00'
	elif hour < 10:
		arrival_hour = '0' + str(hour) + '00 - ' + str(hour + 1) + '00'
	elif hour < 23:
		arrival_hour = str(hour) + '00 - ' + str(hour + 1) + '00'
	else:
		arrival_hour = str(hour) + '00 - 0000'
	return arrival_hour


def extract_flightnumber(ident):
	# extracts flight number from flight identity in the FlightAware API
    return ''.join(list(re.findall(r'\d+', ident)))

def extract_airline(ident):
	# extracts airline number from flight identity in the FlightAware API
    return ''.join(list(re.findall(r'[a-zA-Z]+', ident)))
	
def GmapApi(eta, wait_delta, start_address='****', terminal='2', mode='arriveby'):
	# getssuggested departure time from GooleMapsAPI's distance matrix
	gmaps = googlemaps.Client(key = gmaps_api_key)
	wait_delta = pd.to_timedelta('00:' + str(wait_delta) + ':00')
	out_time = eta + wait_delta
	end_address = 'airport ' + terminal
	directions_result = gmaps.distance_matrix(start_address, end_address, 
                                     mode='driving', 
                                     arrival_time = out_time)
	
	# parse JSON
	start_address = directions_result['origin_addresses'][0]
	end_address = directions_result['destination_addresses'][0]
	distance = directions_result['rows'][0]['elements'][0]['distance']['text']
	duration_text = directions_result['rows'][0]['elements'][0]['duration']['text']
	duration_parts = duration_text.split()
	
	duration = None
	if len(duration_parts) > 2:
		hour = duration_parts[0]
		minute = duration_parts[2]
		duration = hour + ':' + minute + ':00'
	else:
		minute = duration_parts[0]
		duration = '00:' + minute + ':00'
	duration = pd.to_timedelta(duration)
	
	depart_time = out_time - duration
	
	
	return start_address, end_address, distance, wait_delta, out_time, duration_text, duration, depart_time
	
	

def FawApi():
	# gets landing schedule for the next two hours from GlightAware API
	# Due to the API being very expensive, I limited the calls to maximum one per every two hours.
	# The last access time is recorded in accesstime.txt
	en_route_df = None
	accesstime = None
	
	with open('insight/resources/accesstime.txt', "r") as infile:
		accesstime = pd.to_datetime(infile.readline())
	
	en_route_df = pd.read_pickle('insight/resources/act.pkl')	
	# en_route_df['airline'] = en_route_df['ident'].map(extract_airline)
	# en_route_df['flight_number'] = en_route_df['ident'].map(extract_flightnumber)
		
	if datetime.now() - pd.to_timedelta(2, unit='h') < faw_accesstime:
		print('USING EXISTING ROUTES')
		return en_route_df
	else:	
		print('GETTING NEW ROUTES')		
		
		# first set max size of the returned values by query
		payload = {'max_size': '150'}
		response = requests.get(fxmlUrl + "SetMaximumResultSize",
		params=payload, auth=(flight_aware_username, flight_aware_api_key))

		if response.status_code != 200:
			return None

		payload = {'airport':'***', 'howMany':'150', }
		response = requests.get(
		fxmlUrl + "Enroute", params=payload, auth=(flight_aware_username, flight_aware_api_key))

		if response.status_code == 200:
			en_route = response.json()['EnrouteResult']['enroute']
			en_route_df = pd.DataFrame.from_dict(en_route, orient='columns')	
			# eta is GMT time in unix format. First convert unix time to regular and then subtract 7 hours to get LA local time.
			en_route_df['eta'] = pd.to_datetime(en_route_df['estimatedarrivaltime'], unit='s')
			en_route_df['eta'] = [d - pd.to_timedelta(7, unit='h') for d in en_route_df['eta']]
			
			# put time in differrent hour buckets and add it to the dataframe
			en_route_df['hour'] = en_route_df['eta'].map(binize_hour)
			en_route_df = en_route_df.merge(en_route_df.groupby('hour').size().to_frame('flights'),
											left_on='hour', right_on='hour')
											
			en_route_df['airline'] = en_route_df['ident'].map(extract_airline)
			en_route_df['flight_number'] = en_route_df['ident'].map(extract_flightnumber)								
			en_route_df.to_pickle(r"insight/resources/acp.pkl")
			
			# update access time
			with open('insight/resources/accesstime.txt', "w") as infile:
				infile.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
				
			return en_route_df
		
		print('ERROR GETTING ROUTES')
		return None
										
		
	


def CBPModel(**keywargs):
	# applies random forest prediction model to the input data read from FlightAware API to predict the passport checking time.
	# unfortunately, flask has some issues loading the XGBoost model, so here I used the random forest model.
	
	keywargs['date'] = keywargs['date'] - pd.to_timedelta(7, unit='h')
	hour = binize_hour(keywargs['date'])
			
	with open(resources_directory + 'randf.md', "rb") as infile:
		randf = pickle.load(infile)
		
	with open(resources_directory + 'terminal.le', "rb") as infile:
		le_terminal = pickle.load(infile)
	with open(resources_directory + 'hour.le', "rb") as infile:
		le_hour = pickle.load(infile)
	with open(resources_directory + 'dayofweek.le', "rb") as infile:
		le_dayofweek = pickle.load(infile)
	with open(resources_directory + 'monthofyear.le', "rb") as infile:
		le_monthofyear = pickle.load(infile)
	
	d = {'terminal': [keywargs['terminal']], 'hour':hour, 'date': keywargs['date']}
	input = pd.DataFrame(data=d)
	
	input['date'] = pd.to_datetime(input['date'])	
	input['dayofweek'] = input['date'].dt.weekday_name
	monthofyear = input['date'].dt.month_name()
	input['monthofyear'] = monthofyear
	terminal = keywargs['terminal']

	input['flights'] = keywargs['num_flights']
	input['total'] = monthly_passenger_coef[monthofyear.iloc[0]] * terminal_passenger_flow[terminal]
	input['US'] = keywargs['citizenship']
	
	input['terminal'] = le_terminal.transform(input['terminal'])
	input['hour'] = le_hour.transform(input['hour'])
	input['dayofweek'] = le_dayofweek.transform(input['dayofweek'])
	input['monthofyear'] = le_monthofyear.transform(input['monthofyear'])
	
	input = input.drop(['date'], axis=1)
	
	pred = randf.predict(input)[0]
	
	return roundup(pred, 5)
	
	
def BaggageModel(mode):
	# uses an average time (based on published studies) for the baggage claim.
	if mode == 'optimistic':
		return 20
	else:
		return 30

def ACOutModel(row_number):
	# uses a linear regression prediction time for time out of cabin based on published studies.
	ext_time = 5.0 + 0.5 * int(row_number)
	return int(math.ceil(ext_time))