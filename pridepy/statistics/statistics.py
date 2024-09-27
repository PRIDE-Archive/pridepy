import plotly
import plotly.graph_objs as go

from pridepy.util.api_handling import Util

base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"


class Statistics:
    """
    Statistics class supports to produce charts on PRIDE submission statistics.
    """

    @staticmethod
    def plot_monthly_submissions(output_filename):
        """
        Plot monthly submission as a bar chart and save into a file
        :param output_filename: html output file
        :return:
        """

        # get monthly submission data from API
        request_url = base_url + "stats/submissions-monthly"
        headers = {"Accept": "application/JSON"}

        response = Util.get_api_call(request_url, headers)
        response_body = response.json()

        # sort data by past to present
        data = [
            go.Bar(
                x=[d[0] for d in response_body][::-1],
                y=[d[1] for d in response_body][::-1],
            )
        ]

        # plot the data in a bar chart
        plotly.offline.plot(data, filename=output_filename, auto_open=True)

    @staticmethod
    def plot_submissions_by_instrument(output_filename):
        """
        Plot submissions by instruments to visualise the pecentage of submission from different instruments.
        :param output_filename:
        :return: html output file
        """
        # Todo
        pass
