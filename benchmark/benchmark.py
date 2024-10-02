import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# Load the data
data = pd.read_csv("final_benchmark.csv", sep=",")

# Display the first few rows and data info
print(data.head())
print("\nDataframe Info:")
print(data.info())

# Display unique values in the 'Benchmark ID' column
print("\nUnique values in Benchmark ID:")
print(data['Benchmark ID'].unique())

# Ensure 'Benchmark ID' is treated as a category and set the desired order
benchmark_order = ['14M', '230M', '3G', '7G']
data['Benchmark ID'] = pd.Categorical(data['Benchmark ID'], categories=benchmark_order, ordered=True)

# Create the plot
plt.figure(figsize=(12, 6))
ax = sns.boxplot(x="Benchmark ID", y="Average Speed (MB/s)", hue="Method", data=data)

# Customize the plot
plt.title("Average Speed by Protocol and File Size", fontsize=16)
plt.xlabel("File Size (Benchmark ID)", fontsize=12)
plt.ylabel("Average Speed (MB/s)", fontsize=12)
plt.legend(title="Protocol", loc='upper left')

# Explicitly set x-axis labels
ax.set_xticks(range(len(benchmark_order)))
ax.set_xticklabels(benchmark_order)

# Adjust layout to prevent cutting off labels
plt.tight_layout()

# Save the plot to a file
plt.savefig('benchmark.svg', format='svg', dpi=300, bbox_inches='tight')
print("Plot saved as 'benchmark.png'")

# Print the actual x-tick labels after plotting
print("\nActual x-tick labels:")
print([item.get_text() for item in ax.get_xticklabels()])

# Close the plot to free up memory
plt.close()

####################################################################################################

# Define a custom color palette based on the colors in the image
custom_palette = {
    'DE': '#1f77b4',     # Blue
    'GB': '#ff7f0e',  # Orange
    'EBI': '#2ca02c',   # Green
    'US': '#d62728',    # Red
    'HK': '#9467bd',    # Purple
}

# Create the FacetGrid with 'Method' as rows
g = sns.FacetGrid(data, row='Method', height=6, aspect=2, margin_titles=True)

# Map the barplot to each facet, using 'Location' as hue and the custom palette
g.map(sns.barplot, 'Benchmark ID', 'Average Speed (MB/s)', 'Location',
      order=data['Benchmark ID'].unique(), hue_order=data['Location'].unique(),
      palette=custom_palette)

# Add a legend for the 'Location' variable
g.add_legend(title='Location', loc='upper right')

# Set titles for each method (automatically handled by FacetGrid)
g.set_titles(row_template="Method: {row_name}")

# Set axis labels
g.set_axis_labels('Benchmark ID', 'Average Speed (MB/s)')

# Adjust the layout and add a main title
plt.subplots_adjust(top=0.9)
g.fig.suptitle('Average Speed (MB/s) by Location and Method', fontsize=16)

# Save the plot as a high-resolution SVG image
plt.savefig('speed_by_method_location.svg', format='svg', dpi=300, bbox_inches='tight')

# Confirm save and close the plot
print("Plot saved as 'speed_by_method_location.svg'")
plt.close()

####################################################################################################

# Create the plot
plt.figure(figsize=(12, 6))
sns.barplot(x='Benchmark ID', y='Average Speed (MB/s)', hue='Location', data=data)

# Customize the plot
plt.title('Average Speed (MB/s) by Location', fontsize=16)
plt.xlabel('Benchmark ID', fontsize=12)
plt.ylabel('Average Speed (MB/s)', fontsize=12)
plt.legend(title='Location', loc='upper right')

# Adjust layout
plt.tight_layout()

# Save the plot
plt.savefig('average_speed_location', dpi=300, bbox_inches='tight')
print("Plot saved as 'file_size_country_plot.png'")

# Close the plot
plt.close()





