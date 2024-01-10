"""
Created by Or Itzhaki 9.1.24
"""

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from cd02_parse_blood_or import parse_blood
from cd01_utils import viedoc_to_df, convert_to_date
from cd01_parse_response import parse_response


TP_PFS_CURATION_PATH = 'ManualCuration/12122023_TP_PFS_curation.csv'
INPUT_PATH = 'OncoHost_20231224_145142.xlsx'

def get_progression(clin_dict, full_data):
    # eos date, os event, progression + notes, death date
    blood_df = viedoc_to_df(clin_dict['BLOOD'])
    blood_df = blood_df.rename(columns={'Event Id': 'Visit',
                                        'Blood Collection Date:': 'BloodCollectionDate',
                                        'Treatment Date:': 'TreatmentDate',
                                        'Blood Collection Time:': 'BloodCollectionTime',
                                        'End Timefor Plasma Preparation Procedure:': 'EndPrepTime'})
    first_treatment = convert_to_date(blood_df.TreatmentDate[blood_df.Visit == 'PRE'])
    df_dict = parse_response(clin_dict, first_treatment)
    summary_df = df_dict['Summary'][['PFSDateCurated']]
    summary_df_temp = summary_df.add_prefix('NEW_')
    summary_df_temp = summary_df_temp.reset_index()
    TP_curated_df = pd.read_csv(TP_PFS_CURATION_PATH)
    TP_curated_df = TP_curated_df.add_prefix('OLD_')
    TP_curated_df = TP_curated_df.drop(columns=['OLD_Unnamed: 0', 'OLD_OSDateCurated', 'OLD_OSEvent'], axis=1)
    TP_curated_df.rename(columns={'OLD_SubjectId': 'SubjectId'}, inplace=True)
    TP_curated_df['OLD_PFSDateSummary'] = convert_to_date(TP_curated_df['OLD_PFSDateSummary'])
    TP_curated_df['OLD_PFSDateREC'] = convert_to_date(TP_curated_df['OLD_PFSDateREC'])
    response_df = full_data[['SubjectId']]
    merged_pfs_df = pd.merge(response_df, summary_df_temp, on='SubjectId', how='left')
    merged_pfs_df = pd.merge(merged_pfs_df, TP_curated_df, on='SubjectId', how='left')

    def fill_pfs_date(row):
        if row['OLD_TPCurationSummary'] and row['OLD_TPCurationREC']:
            if row['OLD_PFSDateSummary'] == row['OLD_PFSDateREC']:
                row['PFSDate'] = row['OLD_PFSDateSummary']
        elif row['OLD_TPCurationSummary']:
            row['PFSDate'] = row['OLD_PFSDateSummary']
        elif row['OLD_TPCurationREC']:
            row['PFSDate'] = row['OLD_PFSDateREC']
        else:  # F/na & F/na
            row['PFSDate'] = row['NEW_PFSDateCurated']
        return row

    merged_pfs_df['PFSDate'] = ''
    merged_pfs_df['OLD_TPCurationSummary'] = merged_pfs_df['OLD_TPCurationSummary'].fillna(False)
    merged_pfs_df['OLD_TPCurationREC'] = merged_pfs_df['OLD_TPCurationREC'].fillna(False)
    merged_pfs_df = merged_pfs_df.apply(fill_pfs_date, axis=1)
    final_df = pd.merge(full_data, merged_pfs_df[['SubjectId', 'PFSDate']])
    return final_df


if __name__ == "__main__":
    clin_dict = pd.read_excel(INPUT_PATH, sheet_name=None)
    blood_df, treatment_df = parse_blood(clin_dict)
    # filter:
    blood_df = blood_df[blood_df['Indication'] == 'NSCLC']
    blood_df = blood_df[blood_df['BloodCollectionDate'] != 'Not Done']
    # sort:
    blood_df = blood_df.sort_values(['SubjectId', 'BloodCollectionDate'])

    # print(blood_df.columns)
    # blood_df.to_excel('blood_df.xlsx')
    # with open("ids_blood.txt", 'w') as file:
    #     for item in blood_df['SubjectId'].unique():
    #         print(item, file=file)

    #### create summary df
    blood_summary_df = blood_df['SubjectId'].drop_duplicates()
    # get first treatment info:
    first_trt = blood_df[(blood_df['Visit'] == 'PRE') & (blood_df['TreatmentDate'].notna())]
    first_trt = first_trt[['SubjectId', 'TreatmentDate']]
    blood_summary_df = pd.merge(blood_summary_df, first_trt, on='SubjectId', how='left')
    # get progression info:
    blood_summary_df = get_progression(clin_dict, blood_summary_df)
    blood_summary_df.rename(columns={'TreatmentDate': 'FirstTreatmentDate', 'PFSDate': 'ProgressionDate'}, inplace=True)

    # histogram of number of blood samples
    print("According to current NSCLC data from 24.12.23:")
    print(f"- The number of blood collections reported: {len(blood_df)}")
    print(f"- The number of patients with reported blood collections: {len(blood_df['SubjectId'].unique())}")
    sample_counts = blood_df['SubjectId'].value_counts()
    plt.figure(figsize=(10, 6))
    plt.hist(sample_counts, bins=range(1, sample_counts.max() + 2), align='left', edgecolor='black')
    plt.xlabel('Number of Blood Samples', fontsize=14)
    plt.ylabel('Number of Patients', fontsize=14)
    plt.title('Sample Counts per Patient - Before Cleaning', fontsize=16)
    plt.grid(linestyle='--', alpha=0.7)
    plt.xticks(range(1, sample_counts.max() + 1), fontsize=12)
    plt.yticks(fontsize=12)
    plt.savefig('plots/sample_distribution.png')

    # new histogram with cleaned patients with less than two blood samples and no first treatment found
    # filter for no treatment dates
    have_trt_ids = blood_summary_df.loc[blood_summary_df['FirstTreatmentDate'].notna(), 'SubjectId']
    filtered_blood_df = blood_df[blood_df['SubjectId'].isin(have_trt_ids)]
    # filter for at least two samples
    sample_counts_filtered = filtered_blood_df['SubjectId'].value_counts()
    sample_counts_filtered = sample_counts_filtered[sample_counts_filtered >= 2]
    filtered_blood_df = blood_df[blood_df['SubjectId'].isin(sample_counts_filtered.index)]
    print(f"- The number of blood collections reported after cleaning: {len(filtered_blood_df)}")
    print(f"- The number of patients with reported blood collections after cleaning: {len(filtered_blood_df['SubjectId'].unique())}")
    plt.figure(figsize=(10, 6))
    plt.hist(sample_counts_filtered, bins=range(2, sample_counts_filtered.max() + 2), align='left', edgecolor='black')
    plt.xlabel('Number of Blood Samples', fontsize=14)
    plt.ylabel('Number of Patients', fontsize=14)
    plt.title('Sample Counts per Patient - After Cleaning', fontsize=16)
    plt.grid(linestyle='--', alpha=0.7)
    plt.xticks(range(1, sample_counts.max() + 1), fontsize=12)
    plt.yticks(fontsize=12)
    plt.savefig('plots/sample_distribution_filtered.png')

    # add a column to the summary df if the patient has t progression or not and what is the date
    # add a column to the summary df if the patient has t1 or not and what the date is
    # add a column to the summary df if the patient's tprog == t1
    blood_summary_df['PassedFilter'] = False
    blood_summary_df['HasTprog'] = False
    blood_summary_df['TprogDate'] = None
    blood_summary_df['HasT1'] = False
    blood_summary_df['T1Date'] = None
    blood_summary_df['IsTprogAlsoT1'] = False
    filtered_blood_df['IsT0'] = False   # todo: how to classify??
    filtered_blood_df['IsT1'] = False   # todo: assign
    filtered_blood_df['IsTprog'] = False   # todo: assign

    blood_summary_df.set_index('SubjectId', inplace=True)
    # ix = blood_summary_df['SubjectId'].isin(filtered_blood_df['SubjectId'])
    ix = blood_summary_df.index.isin(filtered_blood_df['SubjectId'])
    blood_summary_df.loc[ix, 'PassedFilter'] = True

    # how many patients have progressed at all
    n = len(blood_summary_df[blood_summary_df['PassedFilter'] & blood_summary_df['ProgressionDate'].notna()])
    print(f"From the filtered data, the number of patients that have progressed are: {n}")
    n = len(blood_summary_df[blood_summary_df['PassedFilter'] & blood_summary_df['ProgressionDate'].isna()])
    print(f"From the filtered data, the number of patients that have not progressed at all are: {n}")

    # fill summary columns:
    two_weeks = pd.Timedelta(days=14)
    month_and_half = pd.Timedelta(days=45)
    month = pd.Timedelta(days=30)
    for sub_id, sub_df in filtered_blood_df.groupby('SubjectId'):
        prog_date = blood_summary_df.at[sub_id, 'ProgressionDate']
        trt_date = blood_summary_df.at[sub_id, 'FirstTreatmentDate']
        # calculate t1:
        has_t1 = False
        for _, row in sub_df.iterrows():
            trt_difference = abs((trt_date - row['BloodCollectionDate']))
            if two_weeks <= trt_difference <= month_and_half and not has_t1:
                has_t1 = True
                blood_summary_df.at[sub_id, 'HasT1'] = True
                blood_summary_df.at[sub_id, 'T1Date'] = row['BloodCollectionDate']
            if has_t1:
                break
        # todo: need to check that t0 and t1 are different?
        # calculate tprog:
        if pd.notna(prog_date):
            dates = sub_df['BloodCollectionDate'].values
            target_date = prog_date + pd.DateOffset(months=1)
            chosen_date = min(dates, key=lambda x: abs((x - target_date).days))
            difference = abs((target_date - chosen_date).days)
            if difference <= month.days:
                blood_summary_df.at[sub_id, 'HasTprog'] = True
                blood_summary_df.at[sub_id, 'TprogDate'] = chosen_date
                if has_t1 and chosen_date == blood_summary_df.at[sub_id, 'T1Date']:
                    blood_summary_df.at[sub_id, 'IsTprogAlsoT1'] = True

    # from the patients that have not progressed
    # see the number of patients with and without t progression,

    # of the patients with t progression how many have t1 and how many dont, and how many tprogression == t1

    # do twice 1-Tprog patients with t1  2-Tprog patients withput t1:
    #3 histograms:
    # tprog duration distibution
    # PFS duration distribution
    # the delta between them distribution
    # + which of them have essays for t0, t1, tprog


    # look at the amount of patient with eligibility errors, counts for each error? how many patients with no errors?

    # how many patient have tn's that are not t0,1 or prog
    # distribution?

    # show distribution of t's every time stamp from first treatment ?? check what has to do with progression