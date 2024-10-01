#!/bin/bash
# Please make sure you have installed pridepy (https://github.com/pride-archive/pridepy)
# install shuf if not installed in mac:
# brew install coreutils
# in linux: sudo apt-get install coreutils

# Get country/region info using ipinfo.io
location=$(curl -s https://ipinfo.io/country)

# Define the file categories and corresponding file lists
files_14M=("PXD012474,160219_189_PM_fr14.mgf"
           "PXD010000,Biodiversity_P_polymyxa_TBS_aerobic_3_17July16_Samwise_16-04-10_msgfplus.pride.mztab.gz"
           "PXD004499,D2_Control3_TechRep_1.mzid"
           "PXD017112,Results_MSE_Ssapro_ATCC15305_R3_2.rar"
           "PXD011349,121225_OV1_SE_Heart_failure_Probe_56_Pat_48_LV.pep.xml")

files_230M=("PXD043205,FB_V_243.raw"
            "PXD027964,009_3D_C17_CHECK.raw"
            "PXD006687,4_5.mgf"
            "PXD006277,20140606AdDocHCN107.raw"
            "PXD042361,Demongrp_030519_ip_b11.raw")

files_3G=("PXD006475,Ki6028_2.raw"
          "PXD004694,G2_AV_010712_plus_Fe_1_1_qual_F5.raw.zip"
          "PXD030764,PO21_2_4.baf"
          "PXD047912,230911kw_TSeverinPhosDIA25_S3-B2_1_16487.d.zip"
          "PXD048638,230215_463.rar")

files_7G=("PXD036017,21-Prot-1628_RB6_1_5987.d.rar"
          "PXD040786,schroeter14683.raw.7z"
          "PXD036017,21-Prot-1634_RC4_1_5963.d.rar"
          "PXD009244,20161010_SUVI_OSCC_35.raw.zip"
          "PXD010288,samon_I161214_026.mzXML.gz")

# Function to select random files (Bash alternative to `shuf`)
select_random_files() {
    category_files=("$@")
    selected_files=()
    for i in {1..2}; do
        # Generate random index
        rand_index=$((RANDOM % ${#category_files[@]}))
        selected_files+=("${category_files[$rand_index]}")
        # Remove the selected file to avoid duplicates
        category_files=("${category_files[@]:0:$rand_index}" "${category_files[@]:$((rand_index + 1))}")
    done
    echo "${selected_files[@]}"
}

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
        echo "$location,$benchmark_id,$method,$file_name,$speed MB/s,$duration s"

        # Append result to the CSV file
        echo "$location,$benchmark_id,$method,$file_name,$speed,$duration" >> benchmark_report.csv

        # Clean up the downloaded file
        rm -f "$file_name"
    else
        # If the file is not downloaded, log failure
        echo "$location,$benchmark_id,$method,$file_name,-,-"

        # Append failure result to the CSV file
        echo "$location,$benchmark_id,$method,$file_name,-,-" >> benchmark_report.csv
    fi
}

# Generate report header with file name
echo "Location,Benchmark ID,Method,File Name,Average Speed (MB/s),Total Time (s)" > benchmark_report.csv

# Loop through categories
for category in "14M" "230M" "3G" "7G"; do
    case $category in
        "14M")
            selected_files=($(select_random_files "${files_14M[@]}"))
            ;;
        "230M")
            selected_files=($(select_random_files "${files_230M[@]}"))
            ;;
        "3G")
            selected_files=($(select_random_files "${files_3G[@]}"))
            ;;
        "7G")
            selected_files=($(select_random_files "${files_7G[@]}"))
            ;;
        *)
            echo "Invalid category!"
            exit 1
            ;;
    esac

    # Loop through the selected files for each category
    for file in "${selected_files[@]}"; do
        # Split the accession and file name
        IFS=',' read -r accession file_name <<< "$file"

        # Loop through the methods
        for method in ftp aspera globus; do
            benchmark_download $method $accession $file_name $category
        done
    done
done

echo "Benchmark completed. Results saved to benchmark_report.csv"
