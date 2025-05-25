from flask import Flask, request, redirect, url_for
from markupsafe import escape
from datetime import date, datetime
from os import mkdir, path, remove, listdir
from filecmp import cmp
from json2table import convert
import re
import json
import time

#########
# SETUP #

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1000 * 1000

def verify_dir(dir_path):
    is_init_needed = not(path.exists(dir_path))
    if (is_init_needed):
        mkdir(dir_path)
    return is_init_needed

verify_dir('log_archive')
if verify_dir('log_reports') or not(path.exists('log_reports/report_tracker.json')):
    with open('log_reports/report_tracker.json', 'w') as new_report_tracker:
        json_object = {
            'reports_tracked': 0
        }
        new_report_tracker.write(json.dumps(json_object, sort_keys=True, indent=4))

if verify_dir('issues') or not(path.exists('issues/issue_tracker.json')):
    with open('issues/issue_tracker.json', 'w') as new_issue_tracker:
        json_object = {
            'issues_tracked': 0, 
            'open_issues':0,
            'closed_issues': 0,
        }
        new_issue_tracker.write(json.dumps(json_object, sort_keys=True, indent=4))
if not(path.exists('log_reports/report_map.json')):
    with open('log_reports/report_map.json', 'w') as new_issue_report_map:
        new_issue_report_map.write(json.dumps({ }, sort_keys=True, indent=4))

report_id_length = 9
issue_id_length = 6


###############
# URL ROUTING #
# /

@app.route('/', methods=['GET'])
def home():
    
    return log_report_list()


# /logs

@app.route('/logs', methods=['GET', 'POST'])
def access_logs():

    if request.method == 'GET':
        return redirect(url_for('home'))    #url_for stopped working after containerisation

    if request.method == 'POST':
        print(request.form)
        outcome = process_log(request.files['file'])
        if(outcome == ''):
            return('<p>Log upload processed succesfully!</p>')
        else:
            return(f'<p>The exception already exists under: {outcome}</p>')   
  

@app.route('/logs/<string:report_id>', methods=['GET'])
def access_log_archive(report_id):

    first_rep_occur = find_first_report_occurrence(report_id)
    log_text = ''
    with open(f'log_archive/{first_rep_occur[:8]}/{first_rep_occur[9:]}.txt', 'r') as original_log:
        for line in original_log:
            log_text += f'<p>{escape(line)}</p>'
    return log_text
    

@app.route('/logs/<string:report_id>/datetime', methods=['GET'])
def access_report_date(report_id):

    if len(report_id) == report_id_length:
        return f'<p>First occurred: {find_first_report_occurrence(report_id)}</p>'

    #forgive user entering issue id instead and look for the report by issue
    if len(report_id) == issue_id_length:                   
        with open(f'issues/{report_id}.json') as requested_issue:
            return f'<p>First occurred: {find_first_report_occurrence(json.load(requested_issue)['report_id'])}</p>'
        
    return '<p>ID format not recognized</p>'


@app.route('/logs/extracted/<string:report_id>', methods=['GET'])
def access_log_report(report_id):

    report_path = ''
    for archived_report_path in listdir('log_reports/'):
        if archived_report_path[:report_id_length] == report_id:
            report_path = archived_report_path

    log_text = ''
    with open(f'log_reports/{report_path}', 'r') as extracted_log:
        for line in extracted_log:
            log_text += f'<p>{escape(line)}</p>'
    return log_text


# /issues

@app.route('/issues', methods=['POST', 'GET'])
def access_issues():

    if request.method == 'POST':
        print(request.form)
        outcome = process_issue(request.files['file'], request.form.get('summary'))
        if outcome[0] == 'i':
            return f'<p>Issue already exists as {outcome[1:]}</p>'
        else:
            return f'<p>Issue {outcome} created</p>'
    
    if request.method == 'GET':
        if len(request.args) == 0:
            return issue_list()
        else:
            status_requested = request.args.get('status').lower()
            if  status_requested == 'open':
                return issue_list('Closed')
            if status_requested == 'closed':
                return issue_list('Open')
            else:
                return '<p>To use an argument please provide a valid issue status: (open/closed)</p>'    
    

@app.route('/issues/<string:issue_id>', methods=['GET', 'DELETE', 'PATCH'])
def access_issue(issue_id):

    if(request.method == 'GET'):
        with open(f'issues/{issue_id}.json') as found_issue:
            json_string = json.load(found_issue)
            return convert(json_string)
        
    if(request.method == 'DELETE'):
        #Delete issue(save report id)
        report_id = get_issue_attribute(issue_id, 'report_id')
        remove(f'issues/{issue_id}.json')

        #Delete report log
        for report_path in listdir('log_reports/'):
            if report_path[:report_id_length] == report_id:
                remove(f'log_reports/{report_path}')

        #Delete report-to-issue mapping
        with open('log_reports/report_map.json', 'r+') as report_map:
            rmap_dict = json.load(report_map)
            del rmap_dict[report_id]
            report_map.seek(0)
            report_map.write(json.dumps(rmap_dict, sort_keys=True, indent=4))
            report_map.truncate()
            
        return f'<p>Issue {escape(issue_id)} deleted succesfully.</p>'
    
    if(request.method == 'PATCH'):
        print(request.form)
        current_status = get_issue_attribute(issue_id, "status").lower()
        status_requested = request.form.get('new_status')

        if current_status == 'ghost':
            return f'<p>Please submit the issue first. Log id: {get_issue_attribute(issue_id, 'report_id')}</p>'
        
        if current_status == status_requested.lower():
            return f'<p>The issue is {escape(status_requested)} alraedy. No change made.</p>'
        
        if status_requested.lower() == 'closed':
            update_issue_status(issue_id, 'Closed')
            return f'<p>The issue {escape(issue_id)} is now closed.</p>'

        if status_requested.lower() == 'open':
            update_issue_status(issue_id, 'Open')
            return f'<p>The issue {escape(issue_id)} is now reopened.</p>'

        else:
            return f'<p>status requested: {escape(status_requested)} unrecognized. Accepted: open/closed</p>'


#################
# WEBPAGE LISTS #

def eq_whtspc(new_line, char_index):

    while len(new_line) < char_index:
        new_line += '.'
    return new_line

def issue_list(excluded_status = 'Ghost'):
    home_text = '<p>ISSUE_ID........STATUS....TYPE......OCCUR...SUMMARY</p>'

    for issue_path in listdir('issues/'):
        if issue_path[0] == 'i':
            continue
        new_line = '<p>'
        with open(f'issues/{issue_path}') as next_issue:
            ni_dict = json.load(next_issue)
            if(ni_dict['status'] == 'Ghost' or ni_dict['status'] == excluded_status):   # Ghost issues are never displayed, except when requested directly (but their id's are generally not user-facing)
                continue
            new_line += issue_path[:-5]
            new_line = eq_whtspc(new_line, 16)
            new_line += ni_dict['status']
            new_line = eq_whtspc(new_line, 26)
            new_line += ni_dict['report_type']
            new_line = eq_whtspc(new_line, 36)
            new_line += str(ni_dict['occurrences'])
            new_line = eq_whtspc(new_line, 44)
            new_line += f'{ni_dict['summary']}</p>'

        home_text += new_line

    return home_text


def log_report_list():
    home_text = '<p>LOG_ID............TYPE......OCCUR...FIRST_FOUND</p>'

    def eq_whtspc(new_line, char_index):
        while len(new_line) < char_index:
            new_line += '.'
        return new_line

    for issue_path in listdir('issues/'):
        if issue_path[0] == 'i':
            continue
        new_line = '<p>'
        with open(f'issues/{issue_path}') as next_issue:
            ni_dict = json.load(next_issue)
            new_line += ni_dict['report_id']
            new_line = eq_whtspc(new_line, 18)
            new_line += ni_dict['report_type']
            new_line = eq_whtspc(new_line, 28)
            new_line += str(ni_dict['occurrences'])
            new_line = eq_whtspc(new_line, 36)
            new_line += f'{find_first_report_occurrence(ni_dict['report_id'])}</p>'

        home_text += new_line

    return home_text


####################
# HELPER FUNCTIONS #


# Compares 2 files. Removes the new one if identical and returns True.
# Disregards cases with two identical paths
def de_duplicate(new_file_path, old_file_path):
    if new_file_path == old_file_path:
        return False

    is_match_found = cmp(new_file_path, old_file_path, False)
    if is_match_found:
        remove(new_file_path)

    return is_match_found


# Generates next id for an issue or report from respective tracker and id_digit count
# Does not increment the tracker before, that is postponed and executed by function below
def generate_id(json_path, counter_key, id_digits):
    counter = 0
    with open(json_path) as source:
        counter = json.load(source)[counter_key]
    string_id = str(counter + 1)
    missing_zeros = id_digits - len(string_id)
    while(missing_zeros > 0):
        string_id = f'0{string_id}'
        missing_zeros -= 1
    return string_id


def increment_tracker(path, key):
    with open(path, 'r+') as tracker:
        tracker_dict = json.load(tracker)
        tracker_dict[key] += 1
        tracker.seek(0)
        tracker.write(json.dumps(tracker_dict, sort_keys=True, indent=4))
        tracker.truncate()


# Isolates report id from its system path
def rep_id_from_path(report_path):
    return report_path[12:12+report_id_length]


# Gets requested value from issue .json file
def get_issue_attribute(issue_id, attribute):
    with open(f'issues/{issue_id}.json') as requested_issue:
        return json.load(requested_issue)[attribute]


# Gets the date associated log was first recorded
def find_first_report_occurrence(report_id):
    for report_path in listdir('log_reports/'):
        if report_path[:report_id_length] == report_id:
            return report_path[report_id_length+1:-4]
    return 'not found'    


# Gets issue id from report_map.json
def get_issue_by_report(report_id):
    with open('log_reports/report_map.json') as report_map:
        return json.load(report_map)[report_id]
    

def increment_occurrence(id):
    issue_id = ''
    if len(id) == issue_id_length:
            issue_id = id
    elif len(id) == report_id_length:
            issue_id == get_issue_by_report(id)

    with open(f'issues/{id}.json', 'r+') as issue_occurring:
        issue_dict = json.load(issue_occurring)
        issue_dict['occurrences'] += 1
        issue_occurring.seek(0)
        issue_occurring.write(json.dumps(issue_dict, sort_keys=True, indent=4))
        issue_occurring.truncate()


##################
# MAIN FUNCTIONS #

def process_log(log_attachment, log_only = True):
    if not(path.exists(f'log_archive/{datetime.strftime(date.today(), r'%y-%m-%d')}')):
        mkdir(f'log_archive/{datetime.strftime(date.today(), r'%y-%m-%d')}')

    with open(f'log_archive/{datetime.strftime(date.today(), r'%y-%m-%d')}/{datetime.strftime(datetime.today(), '%H.%M.%S')}.txt', 'w') as new_log:
        
        new_report = ''
        new_report_path = ''

        exception = None                  
        class Exception_interpreter:
            type = ''                     # 'C' - Crash    'E' - Error    'W' - Warning

            is_stack_detected = False
            check_special_stack = False

            def _translate(self, exception_found):
                exc_fnd_low_case = exception_found.lower()
                match exc_fnd_low_case:
                    case 'callstack':
                        self.check_special_stack = True
                        return 'C'
                    case '==============================================================================':
                        self.is_stack_detected ^= True
                        return 'C'
                    case 'error':
                        return 'E'
                    case 'warning':
                        return 'W'
                    
            def __init__(self, search_outcome):
                self.type = self._translate(search_outcome)

            def update_exception(self, search_outcome):
                new_code = self._translate(search_outcome)

                if self.type ==  'W':
                    self.type = new_code
                elif new_code == 'C':
                    self.type = new_code

            def toggle_spec_stack_rec(self):              
                if self.is_stack_detected:
                    self.is_stack_detected = False
                    self.check_special_stack = False
                else:
                    self.is_stack_detected = True


        for line in log_attachment:
            decoded_line = line.decode()
            new_log.writelines(decoded_line)

            exception_in_line = False
            exception_found = re.search(r'(?i)callstack|^\={78}', decoded_line)
            if not(exception_found):
                exception_found = re.search('(?i)error', decoded_line)
                if not(exception_found):
                    exception_found = re.search('(?i)warning', decoded_line)

            if(exception_found):
                exception_in_line = True

                if not(exception):
                    exception = Exception_interpreter(exception_found[0])
                    new_report_id = generate_id('log_reports/report_tracker.json','reports_tracked', report_id_length)
                    new_report_path = f'log_reports/{new_report_id}-{datetime.strftime(datetime.today(), r'%y-%m-%d-%H.%M.%S')}.txt'
                    new_report = open(new_report_path, 'w', 1)

                else:
                    exception.update_exception(exception_found[0])

            if (exception and exception.type == 'C') and not(exception_in_line):
                if exception.check_special_stack:
                    if decoded_line == '\r\n' or decoded_line == '\n':
                        exception.toggle_spec_stack_rec()
                    else:
                        if not(exception.is_stack_detected):
                            exception.check_special_stack = False

            if exception_in_line or (exception and exception.is_stack_detected):
                
                new_report.writelines(decoded_line)


        if exception:
            new_report.close

            for archived_report_path in listdir('log_reports/'):
                
                if de_duplicate(new_report_path, f'log_reports/{archived_report_path}'):
                    print('identical report already exists')
                    related_issue_id = get_issue_by_report(archived_report_path[:report_id_length])
                    
                    if(log_only):
                        increment_occurrence(related_issue_id)
                        return archived_report_path[:report_id_length]
                    
                    if get_issue_attribute(related_issue_id, 'status') == 'Ghost':
                        print('it was ghost')
                        return (f'g{(related_issue_id)}')

                    else:
                        increment_occurrence(related_issue_id)
                        print('it was full report')
                        return ('i' + related_issue_id)
            
            print('report is new')            

            increment_tracker('log_reports/report_tracker.json', 'reports_tracked')
            if(log_only):
                # Ghost issues mostly keep track of issue occurences until it is manually posted
                add_issue('Ghost', '', rep_id_from_path(new_report_path), exception.type)
                return ''
            
    return(f'{exception.type}{rep_id_from_path(new_report_path)}')


def process_issue(log_attachment, summary):
    log_analysis_outcome = process_log(log_attachment, False)
    print('log analysis outcome:' + log_analysis_outcome)
    if log_analysis_outcome[0] == 'g':    #issue previously recorded as ghost                      
        with open(f'issues/{log_analysis_outcome[1:]}.json', 'r+') as partial_report:
            part_rep_dict = json.load(partial_report)
            part_rep_dict['status'] = 'Open'
            part_rep_dict['summary'] = summary
            part_rep_dict['occurrences'] += 1
            partial_report.seek(0)
            partial_report.write(json.dumps(part_rep_dict, sort_keys=True, indent=4))
            partial_report.truncate()
        return log_analysis_outcome[1:]

    if log_analysis_outcome[0] == 'i':    #issue already exists
        return log_analysis_outcome

    else:    #new issue
        add_issue('Open', summary, log_analysis_outcome[1:], log_analysis_outcome[:1])
        return log_analysis_outcome[1:]


def add_issue(status, summary, report_id, report_type):
    issue_object = {
        'status': status,
        'summary': summary,
        'occurrences': 1,
        'report_id': report_id,        
        'report_type': report_type
    }
    issue_id = generate_id('issues/issue_tracker.json', 'issues_tracked', issue_id_length)
    with open(f'issues/{issue_id}.json', 'w') as new_issue:
        new_issue.write(json.dumps(issue_object, sort_keys=True, indent=4))

    increment_tracker('issues/issue_tracker.json', 'issues_tracked')

    with open('log_reports/report_map.json', 'ab') as report_map:
        report_map.seek(-1, 2)
        report_map.truncate()
        if report_map.tell() > 4:
            report_map.write((f', ').encode())
        report_map.write((f'"{report_id}": "{issue_id}"}}').encode())


def update_issue_status(issue_id, new_status):
    with open(f'issues/{issue_id}.json', 'r+') as issue_updated:
        ispa_dict = json.load(issue_updated)
        ispa_dict['status'] = new_status
        issue_updated.seek(0)
        issue_updated.write(json.dumps(ispa_dict, sort_keys=True, indent=4))
        issue_updated.truncate
    

