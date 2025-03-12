from flask import Flask, request, jsonify, render_template, url_for,send_from_directory
import os
import logging
import threading
import pandas as pd
from datetime import date, timedelta, datetime
import yfinance as yf
from pandas_datareader import data as pdr
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3
import json
import http.client
from botocore.exceptions import ClientError
import numpy as np
import time

app = Flask(__name__)
yf.pdr_override()

#Global variables
scale, service = 1, 'a'
h, d, t, p, transaction_type = 0, 0, 0, 0, None
warmup_status, terminated_status = {}, False
instance_public_dns, instance_public_ips, instance_ids = [], [], []
var95, var99, profit_loss_list_buy, profit_loss_list_sell = [], [], [], []
avg_95, avg_99, tot_profit_loss = 0.0, 0.0, 0.0
billable_time_warmup, cost_warmup = 0.0, 0.0
billable_time_total, cost_total, chart_link, endpoint_status = 0.0, 0.0, ' ', 'None'


@app.route('/warmup', methods=['POST'])
def warmup():
    global service, scale
    request_data = request.get_json()
    service = request_data.get('s')
    scale = int(request_data.get('r'))

    if scale > 9:
        return jsonify({'error': 'Scale value must be lower than 10'}), 400

    warmup_status[service] = False

    #Might delete later
    app.config['SERVICE'] = service
    app.config['SCALE'] = scale

    #So we can return 200 immediately and start the real warmup elsewhere
    threading.Thread(target=warmup_service).start()
    return jsonify({'result': 'ok'}), 200

def warmup_service():
    global billable_time_warmup, terminated_status, endpoint_status, cost_warmup, instance_ids, instance_public_dns,instance_public_ips, warmup_status, service
    service = app.config.get('SERVICE')
    scale = app.config.get('SCALE')
    if service == 'lambda':
        api_host = "wapfdx9t7f.execute-api.us-east-1.amazonaws.com"
        api_path = "/default/MonteCarloSimulation1"
        warmup_payload = json.dumps({'is_warmup': True})
        headers = {'Content-type': 'application/json'}

        def fetch_data():
            connection = http.client.HTTPSConnection(api_host)
            try:
                connection.request("POST", api_path, body=warmup_payload, headers=headers)
                response = connection.getresponse()
                data = response.read()
                data_json = json.loads(data.decode('utf-8'))
    
            except Exception as e:
                print(f"Failed to warmup: {str(e)}")
            finally:
                connection.close()

        #Start timer for the warmup call
        start_time = time.time()
        #Threadpool to handle requests
        #Inspired from the code at https://docs.python.org/3/library/concurrent.futures.html
        with ThreadPoolExecutor(max_workers=scale) as executor:
            futures = [executor.submit(fetch_data) for _ in range(scale)]
            for future in futures:
                future.result()
        #End warmup time
        
        billable_time_warmup = (time.time() - start_time)* scale
        #Cost for warmup calculation
        cost_warmup = (billable_time_warmup* 0.125 * 0.0000166667)
        #0.0000166667 is the cost per Gb per second
        #0.125 is the gigabytes used, because 128 Mb are 0.125 Gb

        warmup_status[service] = True
        terminated_status = True #I set True here because lambda functions do not need to be terminated
        endpoint_status = 'warmup'


    if service == 'ec2':
        api_host = "fh0s0tu3w2.execute-api.us-east-1.amazonaws.com"
        api_path = "/default/create_ec2_instance"
        warmup_payload = json.dumps({'scale': scale})
        headers = {'Content-type': 'application/json'}
        start_time = time.time()
        connection = http.client.HTTPSConnection(api_host)
        try:
            connection.request("POST", api_path, body=warmup_payload, headers=headers)
            response = connection.getresponse()
            data = response.read()
            data_json = json.loads(data.decode('utf-8'))
            body_data = json.loads(data_json['body'])
            instance_ids = body_data['instance_ids']

            while True:
                #Here we check the instance status and return only when ready
                check_payload = json.dumps({'instance_ids': instance_ids})
                connection.request("POST", api_path, body=check_payload, headers=headers)
                response = connection.getresponse()
                data = response.read()
                data_json = json.loads(data.decode('utf-8'))
                body_data = json.loads(data_json['body'])

                if isinstance(body_data, list) and len(body_data) > 0 and 'instance_id' in body_data[0]:
                    instance_public_dns = [instance['public_dns'] for instance in body_data]
                    instance_public_ips = [instance['public_ip'] for instance in body_data]
                    break

                time.sleep(5)

        except Exception as e:
            print(f"Failed to warmup  : {str(e)}")
        finally:
            connection.close()

        billable_time_warmup = (time.time() - start_time)* scale
        #Cost calculation for warmup 
        cost_warmup = (billable_time_warmup* (0.0116 / 3600))
        #$0.0116 per hour or $0.0116/3600 per second
        # Prices found on https://aws.amazon.com/ec2/instance-types/t2/
        terminated_status = False
        warmup_status[service] = True
        endpoint_status = 'warmup'


@app.route('/scaled_ready', methods=['GET'])
def scaled_ready():
    is_ready = warmup_status.get(service)
    return jsonify({'warm': str(is_ready).lower()}), 200


@app.route('/get_warmup_cost', methods=['GET'])
def get_warmup_cost():
    global billable_time_warmup, cost_warmup
    return jsonify({'billable_time': str(billable_time_warmup), 'cost': str(cost_warmup)})


'''
The functions fetch_yahoo(), detect_signals() are inspired from
Prof. Lee Gillam's code from the Cloud Computing Coursework assignment
at University of Surrey.
'''


#This function can also receive different Stock symbols anddays_past for a different analysis
def fetch_yahoo(stock_symbol='GOOG', days_past=1095):
    start_date = date.today() - timedelta(days=days_past)
    data = pdr.get_data_yahoo(stock_symbol, start=start_date, end=date.today())
    return data

def detect_signals(data, signal_type, minhistory, p):
    data['Buy'], data['Sell'],  = 0, 0
    data['mean'], data['std'],  = 0, 0
    data['Profit'] = np.nan
    body = 0.01
    for i in range(2, len(data)):
        #Three White Soldiers
        if signal_type == 'buy':
            if (data.Close[i] - data.Open[i]) >= body \
            and data.Close[i] > data.Close[i-1] \
            and (data.Close[i-1] - data.Open[i-1]) >= body \
            and data.Close[i-1] > data.Close[i-2] \
            and (data.Close[i-2] - data.Open[i-2]) >= body:
                data.at[data.index[i], 'Buy'] = 1
                data.at[data.index[i], 'mean'] = data.Close[i-minhistory:i].pct_change().mean()
                data.at[data.index[i], 'std'] = data.Close[i-minhistory:i].pct_change().std()
                if (i+p < len(data)):
                    data.at[data.index[i], 'Profit'] = (data.Close[i+p])-(data.Close[i])

        #Three Black Crows
        else:
            if (data.Open[i] - data.Close[i]) >= body \
            and data.Close[i] < data.Close[i-1] \
            and (data.Open[i-1] - data.Close[i-1]) >= body \
            and data.Close[i-1] < data.Close[i-2] \
            and (data.Open[i-2] - data.Close[i-2]) >= body:
                data.at[data.index[i], 'Sell'] = 1
                data.at[data.index[i], 'mean'] = data.Close[i-minhistory:i].pct_change().mean()
                data.at[data.index[i], 'std'] = data.Close[i-minhistory:i].pct_change().std()
                if (i+p < len(data)):
                    data.at[data.index[i], 'Profit'] = (data.Close[i]) - (data.Close[i+p])

        """
        We perform calculations for mean, standard deviation and profit within this function to enhance efficiency. 
        This approach minimizes data access overhead by using the existing access to the 'i'th entry 
        of the 'data' DataFrame. Values are stored directly in the 'mean' and 'std' columns to optimise
        operations and to avoid the need for additional use of pandas in the lambda function.
        """

    return data

def prepare_data(data_and_signals, h, p):
    data_and_signals = data_and_signals.iloc[h:-p]
    #Trim the first 'h' entries to avoid NaN values
    #Trim the last 'p' entries because we cannot calculate profit
    buy_list = data_and_signals['Buy'].tolist()
    sell_list = data_and_signals['Sell'].tolist()
    close_list = data_and_signals['Close'].tolist()
    mean_list = data_and_signals['mean'].tolist()
    std_list = data_and_signals['std'].tolist()
    #The profit value is separated depending on the transaction type
    #NaN values are removed
    temp_profit_buy = data_and_signals[(data_and_signals['Buy'] == 1) & (~data_and_signals['Profit'].isna())]
    profit_loss_list_buy = temp_profit_buy['Profit'].tolist()
    temp_profit_sell = data_and_signals[(data_and_signals['Sell'] == 1) & (~data_and_signals['Profit'].isna())]
    profit_loss_list_sell = temp_profit_sell['Profit'].tolist()
    return (buy_list, sell_list, close_list, mean_list, std_list, profit_loss_list_buy, profit_loss_list_sell)



def generate_chart_link():
    global var95, var99, avg_95, avg_99, chart_link
    chart_data = [
        ['Index', '95% VaR', '99% VaR'],
    ]
    for i in range(len(var95)):
        chart_data.append([i, var95[i], var99[i]])
    rendered_html = render_template('risk_chart.html', chart_data=chart_data, avg_95=avg_95, avg_99=avg_99)
    tmp_path = '/tmp/generated_risk_chart.html'
    with open(tmp_path, 'w') as file:
        file.write(rendered_html)
    chart_link = 'https://cwprojectfin.nw.r.appspot.com/generated_risk_chart'  #The link returned will be always the same unless it is manually changed here
    return chart_link



@app.route('/analyse', methods=['POST'])
def analyse():
    global h, d, t, p, chart_link, endpoint_status, transaction_type, instance_public_dns, instance_public_dns, instance_ids
    request_data = request.get_json()

    h = int(request_data.get('h'))
    d = int(request_data.get('d'))
    t = request_data.get('t')
    p = int(request_data.get('p'))
    transaction_type = t

    update_analyse_values(h, d, t, p)
    #Fetch financial data
    data = fetch_yahoo()
    if data.empty:
        return jsonify({'error': 'No data found'}), 404
    
    #Detect signals based on the transaction type
    global profit_loss_list_buy, profit_loss_list_sell
    data_and_signals = detect_signals(data, signal_type = t, minhistory = h, p=p)
    buy_list, sell_list, close_list, mean_list, std_list, profit_loss_list_buy, profit_loss_list_sell = prepare_data(data_and_signals, h, p)
    
    lambda_response = None
    ec2_response = None

    if (service == 'lambda'):
        lambda_response = invoke_lambda_simulation(d, t, buy_list, sell_list, mean_list, std_list)
    
    elif service == 'ec2':
        ec2_response = invoke_ec2_simulation(d, t, buy_list, sell_list, mean_list, std_list)


    global tot_profit_loss
    if t == 'buy':
        tot_profit_loss = sum(profit_loss_list_buy)
    elif t == 'sell':
        tot_profit_loss = sum(profit_loss_list_sell)


    chart_link = generate_chart_link()
    write_audit()
    endpoint_status = 'analysis'

    #return 'result': 'ok'
    if lambda_response is not None or ec2_response is not None:
        return jsonify({'result': 'ok'}), 200
    else:
        return jsonify({'error': 'Service not available or not specified'}), 500


def update_analyse_values(h_val, d_val, t_val, p_val):
    global h, d, t, p
    h = h_val
    d = d_val
    t = t_val
    p = p_val
    return (h, d, t, p)


def invoke_lambda_simulation(d, t, buy_list, sell_list, mean_list, std_list):
    api_host = "wapfdx9t7f.execute-api.us-east-1.amazonaws.com"
    api_path = "/default/MonteCarloSimulation1"
    payload = json.dumps({
        'd': d,
        't': t,
        'buy_list': buy_list,
        'sell_list': sell_list,
        'mean_list': mean_list,
        'std_list': std_list,
    })
    headers = {'Content-type': 'application/json'}

    def fetch_data():
        connection = http.client.HTTPSConnection(api_host)
        try:
            connection.request("POST", api_path, body=payload, headers=headers)
            response = connection.getresponse()
            if response.status == 200:
                #We need to do this for the way I setup my lambda response in return
                response_data = response.read().decode()
                response_json = json.loads(response_data)
                return json.loads(response_json['body'])
            else:
                print(f"Errors  : {response.reason}")
                return None
        except Exception as e:
            print(f"Exception in fetch_data: {str(e)}")
            return None
        finally:
            connection.close()

    all_var95_lists = []
    all_var99_lists = []

    #Time cost for lambda
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=scale) as executor:
        futures = [executor.submit(fetch_data) for _ in range(scale)]
        #I used 'as_completed' because the order of the lists returned does not matter 
        #As long as I can average out the lists values.
        for future in as_completed(futures):
            result = future.result()
            if result:
                all_var95_lists.append(result.get('var95_list', []))
                all_var99_lists.append(result.get('var99_list', []))
    global billable_time_total, cost_total
    billable_time_total = (time.time() - start_time) * scale
    #Cost for lambda analyse calculation
    cost_total = (billable_time_total* 0.125 * 0.0000166667)

    #Here the values in returned the averaged values from the transponded lists (all_var95_list is a list of lists) 
    if all_var95_lists and all_var99_lists:
        final_var95_list = [sum(items) / len(items) for items in zip(*all_var95_lists)]
        final_var99_list = [sum(items) / len(items) for items in zip(*all_var99_lists)]

        update_var95(final_var95_list, final_var99_list)
        global avg_95, avg_99
        avg_95 = sum(final_var95_list)/len(final_var95_list)
        avg_99 = sum(final_var99_list)/len(final_var99_list)

        return jsonify({'result': 'ok'}), 200
    else:
        return None

#Exact same logic is applied for the ec2 instance, we use a POST request
#the input size was too large for a GET method
def invoke_ec2_simulation(d, t, buy_list, sell_list, mean_list, std_list):
    def fetch_data(instance_ip):
        payload = {
            'd': d,
            't': t,
            'buy_list': buy_list,
            'sell_list': sell_list,
            'mean_list': mean_list,
            'std_list': std_list
        }
        headers = {'Content-type': 'application/json'}
        api_path = "/cgi-bin/monte_carlo.py"
        
        try:
            connection = http.client.HTTPConnection(instance_ip)
            #POST request defined here below 
            connection.request("POST", api_path, body=json.dumps(payload), headers=headers)
            response = connection.getresponse()
            if response.status == 200:
                response_data = response.read().decode()
                response_json = json.loads(response_data)
                return response_json
            else:
                print(f"Errors from {instance_ip}: {response.reason}")
                return None
        except Exception as e:
            print(f"Errors {instance_ip}: {str(e)}")
            return None
        finally:
            connection.close()

    all_var95_lists = []
    all_var99_lists = []

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=scale) as executor:
        futures = [executor.submit(fetch_data, ip) for ip in instance_public_dns]
        for future in as_completed(futures):
            result = future.result()
            if result:
                all_var95_lists.append(result.get('var95_list', []))
                all_var99_lists.append(result.get('var99_list', []))

    global billable_time_total, cost_total
    billable_time_total = (time.time() - start_time) * scale
    cost_total = (billable_time_total * (0.0116 / 3600))

    if all_var95_lists and all_var99_lists:
        final_var95_list = [sum(items) / len(items) for items in zip(*all_var95_lists)]
        final_var99_list = [sum(items) / len(items) for items in zip(*all_var99_lists)]

        update_var95(final_var95_list, final_var99_list)
        global avg_95, avg_99
        avg_95 = sum(final_var95_list) / len(final_var95_list)
        avg_99 = sum(final_var99_list) / len(final_var99_list)

        return jsonify({'result': 'ok'}), 200
    else:
        return None




def write_audit():
    api_host = "rrdc0h6pih.execute-api.us-east-1.amazonaws.com"
    api_path = "/default/create_audit"
    payload = json.dumps({
        "s": service,
        "r": scale,
        "h": h,
        "d": d,
        "t": t,
        "p": p,
        "profit_loss": tot_profit_loss,
        "av95": avg_95,
        "av99": avg_99,
        "time": billable_time_total,
        "cost": cost_total
        })

    headers = {'Content-type': 'application/json'}
    connection = http.client.HTTPSConnection(api_host)
    try:
        connection.request("POST", api_path, body=payload, headers=headers)
        response = connection.getresponse()
        response_data = response.read().decode('utf-8')
        
        if response.status == 200:
            print("Audit updated")
        else:
            print(f"Failed {response.status}, Response : {response_data}")
    
    except Exception as e:
        print(f"Exception  : {str(e)}")
    
    finally:
        connection.close()


def update_var95(var95_list, var99_list):
    global var95, var99
    var95 = var95_list
    var99 = var99_list


@app.route('/get_sig_vars9599', methods=['GET'])
def get_sig_vars9599():
    global var95, var99

    return jsonify({'var95': str(var95), 'var99': str(var99)})

@app.route('/get_avg_vars9599', methods=['GET'])
def get_avg_vars9599():
    global avg_95, avg_99

    return jsonify({'var95': str(avg_95), 'var99': str(avg_99)})


@app.route('/get_sig_profit_loss', methods=['GET'])
def get_sig_profit_loss():
    global profit_loss_list_buy, profit_loss_list_sell, transaction_type
    if transaction_type == 'buy':
        profit_loss_list = profit_loss_list_buy
    elif transaction_type == 'sell':
        profit_loss_list = profit_loss_list_sell
    else:
        return jsonify({'error': 'Invalid transaction_type '}), 400

    return jsonify({'profit_loss': str(profit_loss_list)})

@app.route('/get_tot_profit_loss', methods=['GET'])
def get_tot_profit_loss():
    global tot_profit_loss
    return jsonify({'profit_loss': str(tot_profit_loss)})


@app.route('/generated_risk_chart')
def serve_generated_risk_chart():
    return send_from_directory('/tmp', 'generated_risk_chart.html')

@app.route('/get_chart_url', methods=['GET'])
def get_chart_url():
    global chart_link
    return jsonify({'url: ': str(chart_link)})


@app.route('/get_time_cost', methods=['GET'])
def get_time_cost():
    global billable_time_total, cost_total
    return jsonify({'time': str(billable_time_total), 'cost': str(cost_total)})


@app.route('/get_audit', methods=['GET'])
def get_audit():
    api_host = "ux9r84sa86.execute-api.us-east-1.amazonaws.com"
    api_path = "/default/read_audit"

    headers = {'Content-type': 'application/json'}
    connection = http.client.HTTPSConnection(api_host)
    
    try:
        connection.request("GET", api_path, headers=headers)
        response = connection.getresponse()
        response_data = response.read().decode('utf-8')
        response_json = json.loads(response_data)
        body_content = response_json.get('body', response_json)
        #Converted here
        if isinstance(body_content, str):
            body_content = json.loads(body_content)
        return (json.dumps(body_content, indent=4))
    except Exception as e:
        return jsonify({'errors ': str(e)}), 500
    finally:
        connection.close()


@app.route('/reset', methods=['GET'])
def reset():
    global var95, var99, avg_95, avg_99, profit_loss_list_buy, profit_loss_list_sell, tot_profit_loss, billable_time_warmup, cost_warmup, billable_time_total, cost_total, chart_link, endpoint_status
    #Reset all the global variables that have results in them
    var95 = []
    var99 = []
    avg_95 = 0.0
    avg_99 = 0.0
    profit_loss_list_buy = []
    profit_loss_list_sell = []
    tot_profit_loss = 0.0
    billable_time_warmup = 0.0
    cost_warmup = 0.0
    billable_time_total = 0.0
    cost_total =0.0
    chart_link = ' '
    endpoint_status = 'warmup'
    
    return jsonify({'result': 'ok'}), 200


def call_terminate_lambda():
    global instance_ids
    api_host = "z5m5zeee6a.execute-api.us-east-1.amazonaws.com"
    api_path = "/default/terminate_instances"
    payload = json.dumps({'terminate_instance_ids': instance_ids})
    headers = {'Content-type': 'application/json'}

    connection = http.client.HTTPSConnection(api_host)
    try:
        connection.request("POST", api_path, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read().decode('utf-8')
        data_json = json.loads(data)
        if data_json.get('statusCode') == 200:
            body_data = json.loads(data_json.get('body', '{}'))
            instance_ids = body_data.get('instance_ids', [])
        threading.Thread(target=check_termination_status).start()
        
    except Exception as e:
        print(f"Failed API invoke : {str(e)}")
    finally:
        connection.close()

def check_termination_status():
    global terminated_status, instance_ids
    api_host = "z5m5zeee6a.execute-api.us-east-1.amazonaws.com"
    api_path = "/default/terminate_instances"
    headers = {'Content-type': 'application/json'}

    while not terminated_status:
        payload = json.dumps({'instance_ids': instance_ids})
        connection = http.client.HTTPSConnection(api_host)
        try:
            connection.request("POST", api_path, body=payload, headers=headers)
            response = connection.getresponse()
            data = response.read().decode('utf-8')
            data_json = json.loads(data)
            body_data = json.loads(data_json.get('body', '{}'))
            if body_data.get('terminated'):
                terminated_status = True
                #Check with debug print
                #TODO remove it if it works
                print("Instances terminated ")
                break
            else:
                time.sleep(5)
        except Exception as e:
            print(f"Errors: {str(e)}")
            break
        finally:
            connection.close()


@app.route('/terminate', methods=['GET'])
def terminate():
    global scale, service, endpoint_status, h, d, t, p, transaction_type, instance_public_dns, instance_public_ips, instance_ids
    if service == 'ec2':
        #Just like the /warmup, we need to return 200 immediately, so here we give the task to check
        #To another thread
        threading.Thread(target=call_terminate_lambda).start()
    
    #Reset also these global variables
    scale = 1
    service = 'a'
    h, d, t, p = 0 , 0, 0 , 0
    transaction_type = None
    endpoint_status = 'None'
    instance_public_dns, instance_public_ips, instance_ids = [], [], []
    
    return jsonify({'result': 'ok'}), 200

@app.route('/scaled_terminated', methods=['GET'])
def scaled_terminated():
    return jsonify({'terminated': str(terminated_status)})

@app.route('/get_endpoints', methods=['GET'])
def get_endpoints():
    global endpoint_status
    endpoint_list = []
    if endpoint_status == 'warmup':
        endpoint_list = [
            {"endpoint": 'curl -X POST https://cwprojectfin.nw.r.appspot.com/analyse -H "Content-Type: application/json" -d "{"h": "105", "d": "10000", "t": "buy", "p": "7"}"'},
            {"endpoint": 'curl -X GET https://cwprojectfin.nw.r.appspot.com/get_warmup_cost'}
        ]
    elif endpoint_status == 'analysis':
        endpoint_list = [
            {"endpoint": 'curl -X GET https://cwprojectfin.nw.r.appspot.com/get_time_cost'},
            {"endpoint": 'curl -X GET https://cwprojectfin.nw.r.appspot.com/get_sig_vars9599'},
            {"endpoint": 'curl -X GET https://cwprojectfin.nw.r.appspot.com/get_avg_vars9599'},
            {"endpoint": 'curl -X GET https://cwprojectfin.nw.r.appspot.com/get_sig_profit_loss'},
            {"endpoint": 'curl -X GET https://cwprojectfin.nw.r.appspot.com/get_tot_profit_loss'},
            {"endpoint": 'curl -X GET https://cwprojectfin.nw.r.appspot.com/get_audit'},
            {"endpoint": 'curl -X GET https://cwprojectfin.nw.r.appspot.com/get_chart_url'},
            {"endpoint": 'curl -X GET https://cwprojectfin.nw.r.appspot.com/reset'},
            {"endpoint": 'curl -X GET https://cwprojectfin.nw.r.appspot.com/terminate'},
            {"endpoint": 'curl -X GET https://cwprojectfin.nw.r.appspot.com/scaled_terminated'}
        ]
    return jsonify(endpoint_list)




if __name__ == '__main__':
    app.run(debug=True, port=8080)
