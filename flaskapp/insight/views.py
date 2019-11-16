from flask import render_template
from insight import app
from flask import request
from insight.model import CBPModel
from insight.model import FawApi
from insight.model import BaggageModel
from insight.model import ACOutModel
from insight.model import GmapApi
from datetime import datetime
import json

def format_time_digit(t):
	if t < 10:
		return '0' + str(t)
	else:
		return str(t)

@app.route('/')
@app.route('/index')
def index():
	user = { 'nickname': 'Keyvan' } # fake user
	return render_template("index.html", title = 'Home', user = user)
	
@app.route('/input')
def flight_input():
	today = datetime.now().date()
	
	en_route_df = FawApi()

	all_flight_numbers = en_route_df[['airline', 'flight_number']].groupby('airline').apply(lambda x: x.to_json(orient='records'))
	
	airline_keys = all_flight_numbers.keys()
	flight_numbers = {}
	for key in airline_keys:
		fls = json.loads(all_flight_numbers[key])
		fl_list = []
    
		for fl in fls:
			fl_list.append(fl['flight_number'])
		flight_numbers[key] = fl_list
	
	user = {'firstname': "Mr.", 'lastname': "My Father's Son"}
	
	return render_template("input.html", today = today, flight_numbers = flight_numbers, user = user)

@app.route('/output')
def arrival_output():
	citizenship = request.args.get('citizenship')
	if citizenship == 'us':
		citizenship = 1
	else:
		citizenship = 0
	
	airline = request.args.get('airline')
	flight = request.args.get('flight')

	terminal = request.args.get('terminal')
	row_number = request.args.get('rownumber')
	start_address = request.args.get('address')
	
	date = datetime.now()
	
	ident = airline + flight	
		
	en_route_df = FawApi()
	route = en_route_df[(en_route_df['ident'] == ident)][['eta', 'flights']]
	
	# if there are multipe flights, for now get the last one until we give the option to the user in future.
	eta = None
	num_flights = None
	if route.iloc[len(route) - 1, 0]:
		eta = route.iloc[len(route) - 1, 0]
		num_flights = route.iloc[len(route) - 1, 1]
		
	
	passport_time = CBPModel(citizenship = citizenship,
								terminal = terminal, 
								date = date,  
								num_flights = num_flights)
								
	baggage_time = BaggageModel('optimistic')
	ac_time = ACOutModel(row_number)
	wait_delta = passport_time + baggage_time + ac_time + 8
	
	
	
	start_address, end_address, distance, wait_delta, out_time, duration_text, duration, depart_time = GmapApi(eta, wait_delta, start_address, terminal)
	
	eta_hour = format_time_digit(eta.hour)
	eta_minute = format_time_digit(eta.minute)
	out_time_hour = format_time_digit(out_time.hour)
	out_time_minute = format_time_digit(out_time.minute)
	depart_time_hour = format_time_digit(depart_time.hour)
	depart_time_minute = format_time_digit(depart_time.minute)
	
	print('eta', eta, 'ac_time', ac_time, 'passport', passport_time, 'baggage', baggage_time)
	
	return render_template("output.html", 
							eta = "%s:%s" % (eta_hour, eta_minute),
							ac_time = ac_time, 
							baggage_time = baggage_time, 
							passport_time = passport_time, 
							start_address = start_address,
							end_address = end_address,
							distance = distance,
							duration = duration_text,
							out_time = "%s:%s" % (out_time.hour, out_time_minute),
							depart_time = "%s:%s" % (depart_time_hour, depart_time_minute))

