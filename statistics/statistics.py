import sys
import requests
import plotly
import plotly.graph_objs as go


"""
This script mainly produces various statistical graphs related to PRIDE archive
"""

base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"


def getMonthlySubmissions(output_filename):

    requestURL = base_url + "stats/submissions-monthly"
    response = requests.get(requestURL, headers={"Accept": "application/JSON"})

    if (not response.ok) or response.status_code != 200:
        response.raise_for_status()
        sys.exit()

    responseBody = response.json()

    data = [go.Bar(
        x=[d[0] for d in responseBody][::-1],
        y=[d[1] for d in responseBody][::-1]
    ),]
    plotly.offline.plot(data, filename=output_filename, auto_open=True)

def getSubmissionsByInstrument():
    pass


if __name__ == '__main__':
    getMonthlySubmissions('monthly-submissions.html')