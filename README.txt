TABLE OF CONTENTS:

1. INTRODUCTION
2. DEPLOYMENT
3. USER MANUAL
4. DESIGN DETAILS


1. INTRODUCTION

Thehis is a simple service that may on one hand accept logs that are sent to it automatically, organise them and track repeating issues, and on the other, 
it may receive manual requests with bug summaries to tie them to organised logs and keep track of understood issues. 

To acheve that the service has three main functionalities:

    + creating a full record of logs recieved (LOGS)

    + identifying and extracting unique failures and exception scenarios (LOG REPORTS)

    + providing an infrastructire for submiting and tracking simple bug tickets (ISSUES)

There are five main routes for the user to get feedback from the process. They respond well to GET requests
sent from a browser:

    + List webpage for captured log reports    /
    + List webpage for submitted bugs           /issues
    + Individual issue view                     /issues/{ISSUE_ID}
    + Log view (fully recovered from archive)   /logs/{LOG_ID}
    + Log extract view                          /logs/extracted/{LOG_ID}

This service was developed on Ubuntu (wsl) and the following instructions are adjusted for that OS.
So far it was only tested as a localhost. Concurrency was not factored in to the design.


2. DEPLOYMENT

The package includes following files: compose.yaml, Dockerfile, L_WS.py, requirements.txt and this very README.txt document.
The compose.yaml provides a simple startup and teardown on a system equipped with docker. 
The data is stored in docker volumes which provide persistence. 

To start the service:
    unload the package into a system directory
    $ cd {path to that directory}
    $ sudo docker compose up

To remove the service:
    $ sudo docker compose down

The script sets up and runs in /app directory


3. USER MANUAL

The script services following URL paths:

/

    [GET]
    This page lists all unique log reports recorded so far. It displays a table including
    - log_ID (9 digits)
    - report_type (C -crash, E - error, W - warning)
    - number of occurrences so far
    - date when its first occurrence was recorded		

/logs

    [POST]
    This endpoint accepts forms enctype="multipart/form-data" with a single log file attached, such as:

        curl -X POST -F "file=@{FILE_PATH}" 127.0.0.1:5000/logs

    The log is recorded and if it has any warnings, errors or crash stacks, 
    a unique log report is extracted and saved with new report id assigned.

    [GET] 
    Redirects to /

/logs/XXXXXXXXX

    [GET]
    This addres (with a 9-digit request id appended) fetches the full text of the original matching log

/logs/XXXXXXXXX/datetime

    [GET]
    This address shows the date of first recorded occurrence associated with report id given

/logs/extracted/XXXXXXXXX

    [GET]
    This addres with 9 digit log report id at the end fetches the reduced version of a log	

/issues

    [GET]
    This page lists all issues submitted to date. It includes follwoing details:
    - issue_ID (6 digits)
    - status (Open or Closed)
    - report_type (C -crash, E - error, W - warning)
    - number of occurrences so far
    - a summary desrcibing the issue

    The list can be filtered by issue status, by passing an URL argument status= with value 'open' or 'closed'

    [POST]
    The same address is an endpoint for requests with bug submissions. 
    Such request needs to have a form of enctype="multipart/form-data" with a single log file attached.
    The form also needs to include a summary attribute with text describing the issue. Example:

        curl -X POST -F "file=@{FILE_PATH}" -F summary='New builds are toast' 127.0.0.1:5000/issues

    Depending on the log attached, the issue will either be associated with an existing log report or,
    if it is new, a new log_report will be extracted from it.

/issues/XXXXXX

    [GET]
    This address (with a 6-digit issue id appended) displays details of a previously submitted issue

    [DELETE]
    A delete request sent to that same addres deletes a previously created issue, along with associated log report.

    [PATCH]
    A patch request may be sent to that same addres with enctype="multipart/form-data" and a new_status attribute
    with value 'open' or 'closed'. The status of associated issue is updated accordingly. Example:

        curl -X PATCH -F new_status='closed' 127.0.0.1:5000/issues/000001


4. DESIGN DETAILS:

This is a summary of how the script operates:

Processing POST request

    Regardless whether a log or a full issue is submitted, the first step is to proces the file stream, store it in
    the log archive and extract any exception lines from it (if found). Those are compared to the existing log reports 
    and, if confirmed to be new, they are saved separtely.
        # One weakness of current implementation is that archived logs are named by current time precise only down to seconds, 
        # which means that if two requests are processed within one second the first log will be overwritten. 
        # Adding fractions of second to log name will substantially resolve this.

    The exception lines are considered to be any lines with 'warning', 'error' or 'callstack' in them. Additionally,
    two extra callstack types are considered: callstacks delineated by linebreaks and by 78 '=' characters. 
    At this stage the issue type is identified tracking the most severe: Crash (assumed with callstack) over Error over Warning
    
    A particular detail of writing the log archive is, that it is conducted with the buffer limited to a single line. The reason for
    this is that, by the time the file comparison started, the standard, fully-buffered write was not completed by the system and,
    with about 30 final lines missing, matches were never found.
        # This choice was made with sacrifice in efficiency. It would be optimal to make the comparison before the file is 
        # written and stored, using data streamed from the request. Furtehmore, writing in byte mode could provide 
        # better balance between resource use and time taken.
    
    The new log report is compared byte by byte with each log report previously created. This is done by filecmp python module
    and it checks for an exact match. 
        # A solution based on degree of similarity would be able to account for case-specific data (eg. user-specific ids
        # or different names of assets of the same type). Something like 90% data match could provide a better classification.
        # To improve efficiency chaging byte-by-byte comparison to comparing hashes or checksums might be preferred.

    Any new log reports trigger creaton of an issue. It is a full open issue in case of a bug submission or a ghost issue,
    in case of a log submission. Ghost issues are like log-report metadata, mostly used to keep track of occurrences. 
    They are upgraded to full issues as soon as a matching bug submission is made. They are not visible on issue lists 
    and can only seen when requested directly by id (which is not typically user-facing).

    If an identical log report or issue is identified, instead an occurrence is counted towards it and the processing is finished. 
    

Adding an issue

    Created issue is named by id and it stores following information:
    {
	status: ['Open' | 'Closed' | 'Ghost']
	summary: 'New builds are toast'
	occurences: 1
	log_id: 000000001
	log_type: ['W' | 'E' | 'C']    # Warning, Error or Crash/Callstack respectively
    }
    Additionally a mapping of report-to-issue is added in the report_map.json
        # The system was designed to sustain more log-reports than issues, but it soon turned out that it runs a parity between them.
        # This made report_map.json essentially obsolete.


Webpage lists

    These lists are collated by parsing all issues recorded to date. The log list focuses on data available in ghost issues plus
    the occurrence date. It is designed to give an idea about all of the logs which were pocessed by the system. On the other hand,
    the issue list ignores ghosts, but in turn it gives a full list of issue properties allowing to track the bugs submitted 
    to the system.
        #These lists need monospace font css very badly.


Server

    The service was only tested on localhost. It runs on a default gunicorn server with a single worker, to avoid
    race conditions or any other concurrency issues.
