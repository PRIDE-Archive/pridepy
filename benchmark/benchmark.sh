#!/bin/bash
# Please make sure you have installed pridepy (https://github.com/pride-archive/pridepy)

# Define project accessions and filenames in separate arrays
benchmark_ids=("14M_file" "230M_file" "3G_file" "7G_file")
accessions=("PXD056312" "PXD056312" "PXD046711" "PXD046711")
file_names=("Ga13HJH_bjhb1_.prot.xml" "Ga13HJH_bjhb1_8.raw" "Seq66990_HFX.raw" "66957-67016_68923-69012_69619-42.zip")

# Function to download and calculate speed for each method
benchmark_download() {
    method=$1
    accession=$2
    file_name=$3
    benchmark_id=$4

    echo "Benchmarking $method for $file_name (Accession: $accession)"

    start_time=$(date +%s)

    # Perform download using pridepy and track success or failure
    case $method in
        ftp)
            pridepy download-file-by-name -a "$accession" -f "$file_name" -o ./ -p ftp
            ;;
        aspera)
            pridepy download-file-by-name -a "$accession" -f "$file_name" -o ./ -p aspera
            ;;
        globus)
            pridepy download-file-by-name -a "$accession" -f "$file_name" -o ./ -p globus
            ;;
        *)
            echo "Invalid method!"
            return
            ;;
    esac

    end_time=$(date +%s)
    duration=$((end_time - start_time))

    # Ensure the file is downloaded before checking size
    if [ -f "$file_name" ]; then
        # Get file size in MB
        file_size=$(du -m "$file_name" | cut -f1)

        # Calculate speed in MB/s
        speed=$(echo "scale=2; $file_size / $duration" | bc)

        # Output result for this method
        echo "$benchmark_id,$method,$speed MB/s,$duration s"

        # Append result to the CSV file
        echo "$benchmark_id,$method,$speed,$duration" >> benchmark_report.csv

        # Clean up the downloaded file
        rm -f "$file_name"
    else
        # If the file is not downloaded, log failure
        echo "$benchmark_id,$method,-,-"

        # Append failure result to the CSV file
        echo "$benchmark_id,$method,-,-" >> benchmark_report.csv
    fi
}

# Generate report header
echo "Benchmark ID,Method,Average Speed (MB/s),Total Time (s)" > benchmark_report.csv

# Loop through benchmarks and methods
for i in "${!benchmark_ids[@]}"; do
    benchmark_id="${benchmark_ids[$i]}"
    accession="${accessions[$i]}"
    file_name="${file_names[$i]}"

    # Loop through the methods
    for method in ftp aspera s3 globus; do
        benchmark_download $method $accession $file_name $benchmark_id
    done
done

echo "Benchmark completed. Results saved to benchmark_report.csv"
