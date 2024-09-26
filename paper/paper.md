---
title: 'pridepy: A Python package to download and search data from PRIDE Archive'
tags:
  - Python
  - proteomics
  - mass spectrometry
  - pride archive
  - big data
authors:
  - name: Selvakumar Kamatchinathan
    affiliation: 1
  - name: Suresh Hewapathirana
    orcid: 0000-0002-7862-5022
    affiliation: 1
  - name: Chakradhar Bandla
    orcid: 0000-0001-6392-3759
    affiliation: 1
  - name: Yasset Perez-Riverol
    orcid: 0000-0001-6579-6941
    affiliation: 1
    
affiliations:
 - name: European Molecular Biology Laboratory, European Bioinformatics Institute (EMBL-EBI), Wellcome Trust Genome Campus, Hinxton, Cambridge CB10 1SD, UK
   index: 1
repository: https://github.com/PRIDE-Archive/pridepy   
date: 26 September 2024
bibliography: paper.bib
---

# Summary
# Summary

`pridepy` is a Python client designed to access the PRIDE Archive `[@Perez-Riverol2022-ow]`, a major public repository for proteomics data. The `pridepy` provides a flexible, programmatic interface to search, retrieve, and download data from the PRIDE Archive via its REST API. This tool simplifies the integration of PRIDE data into bioinformatics pipelines, making it easier for researchers to access large datasets programmatically.

`pridepy` can be easily installed using pip:

# Statement of Need

The PRIDE Archive storages an extensive collection of proteomics data [@Perez-Riverol2022-ow], but manually accessing this data can be inefficient and time-consuming. With the growing need for cloud-based [@Dai2024-yc] and HPC bioinformatics tools [@Mehta2023-og], command-line utilities that seamlessly interact with the PRIDE API are increasingly important. `pridepy` addresses this by enabling researchers to programmatically access PRIDE using Python, a widely adopted language. It allows efficient dataset integration into automated workflows, with support for large-scale data transfers via Aspera, Globus, FTP, and HTTPS, making it ideal for scalable, reproducible pipelines.

# Methods

`pridepy` is built in Python and interacts with the [PRIDE Archive REST API](https://www.ebi.ac.uk/pride/ws/archive/v2/swagger-ui.html). The core functionality includes:

- Searching for datasets using accession numbers or keywords.
- Retrieving and downloading raw files or specific project data using different protocols (e.g., Aspera, Globus, FTP, and HTTPS). This is supported by multiple protocols implemented at the PRIDE Archive (Figure 1).
- Handling biological data types such as proteins and peptides through a high-level interface.
  
The API client leverages Python's request library to handle HTTP requests and responses. It provides a structured approach to query the database, filter results, and download associated files, including mass spectrometry data.

![Figure 1: Architecture of transfer protocols supported by PRIDE Archive](figure.png){ width=80% }

# Usage

The main features of `pridepy` include:
- `download_all_raw_files`: Downloads all raw files for a given project.
- `search_projects_by_keywords_and_filters`: Searches PRIDE Archive projects by keyword, species, instrument, etc.
- `search_protein_evidences`: Retrieves protein evidence associated with a project.

This makes the client suitable for handling large-scale proteomics data in automated workflows, particularly in environments requiring bulk downloads of proteomics datasets.

# Discussion and Future Directions

`pridepy` successfully simplifies access to the PRIDE Archive, but future development could focus on improving the handling of large downloads by implementing parallel downloads or better error handling mechanisms. Additionally, adding more advanced querying capabilities, such as custom filters for specific peptide or protein properties, would make the tool even more powerful for large-scale proteomics analysis. Expanding user documentation and examples could help broaden its use within the scientific community.

# Acknowledgments

We would like to thank the PRIDE Archive team and contributors to this project for their invaluable input and feedback.

# References