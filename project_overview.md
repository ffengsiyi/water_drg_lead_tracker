We already have: 
- all_lead_datasets.csv 
    - a cleaned csv file with water fixture data from all wa state schools
- clean_lead_figures.rmd
    - an R file that creates images based off of the csv

we need to:
- update clean_lead_figures.rmd to work with all_lead_datasets.csv and make sure it works for my own directory
- change clean_lead_figures.rmd to create images based off of district, not county
    - create NEW_clean_lead_figures.rmd through this
    - save the created images as pdfs
- figure out a way to connect the info from all_lead_datasets to clean_lead_figures to align with intended UX

intended UX:
- create a search page for School District Water Lead Testing where users can search up their school district. 
    - use the school_district column in all_lead_datasets.csv
- When they search up the school district, they should be able to see the pdf image for that district, and a report summary. 
    -  report summary will show the district lead testing coverage, district lead remediation cost estimate, and a button to download a detailed report for the given district
        - lead testing example: "61% of schools (27/44) in Kent School District tested drinking water samples, 81% of schools (22/27) were contaminated with lead" 
        - lead remidation example: "Total material costs to replace contaminated fixtures: ~$174,000, $117,000 for tap/sinks (195 over 5 ppb), $57,000 for water fountains (38 over 5 ppb)"
        - the download button should allow the user to download an excel sheet for the district with more detailed information (this might need to be a new script)
- below the image and summary, we want the user to access a dropdown menu to see an estimate cost of water lead remidation table
    - the columns of the table are as follows:
        school, fixture type, fixtures above 5ppb, year of sample collected, unit replacement cost, total estimated cost
            - this information will be primarily scraped from all_lead_datasets.csv 
                - school = school_name
                - fixture type = fixture_type,
                - fixtures above 5ppb = count of the number of "Contaminated" fixtures from contamination_status for the given school_name and fixture_type, 
                - year of sample collected = DOH_testing_round 
                - unit replacement cost = calculated based off of fixutre_type (likely using a different calculation function),
                - total estimated cost = sum of unit replacement cost * fixtures above 5ppb
    - at the end of the table, we will display a total remediation cost for the entire school district

in all_lead_datasets
if: 
    contamination_status = "Contaminated"
then:
    only look at the schools that are associated with the "contaminated" tag

Implementation blockers 
- cant use claude code without a Max or Pro account or without an API key

todo
- cleaned csv file of with only the cols that we need to use for this - only use this file when building the project
- editable text file for the user using claude code
- move the pdf image file to the bottom of the priority list and work on creating the excel csv file that the user needs to download in the end 