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
    cols = ['PFSDateCurated', 'OSDateCurated']
    summary_df = df_dict['Summary'][cols]
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
    final_df = pd.merge(full_data, merged_pfs_df[['SubjectId', 'PFSDate', 'NEW_OSDateCurated']], on='SubjectId',
                        how='left')
    return final_df


def get_progression_duration(row):
    date_dict = {
        'ProgressionDate': row['ProgressionDate'],
        'OSDate': row['OSDate']
    }

    dates = {k: date for (k, date) in date_dict.items() if date not in [pd.NaT, None, '', 'NaT', np.nan]}

    if dates:  # if date exists, take the minimum
        min_date_key = min(dates, key=dates.get)
        row['ProgressionDuration'] = (dates[min_date_key] - row['FirstTreatmentDate']).days
    return row


if __name__ == "__main__":
    clin_dict = pd.read_excel(INPUT_PATH, sheet_name=None)
    original_blood_df, treatment_df = parse_blood(clin_dict)
    # filter:
    original_blood_df = original_blood_df[
        (original_blood_df['Indication'] == 'NSCLC') & ~original_blood_df['SubjectId'].str[:8].isin(['IL-006-9'])]
    blood_df = original_blood_df[original_blood_df['BloodCollectionDate'] != 'Not Done']
    # sort:
    blood_df = blood_df.sort_values(['SubjectId', 'BloodCollectionDate'])

    #### create summary df
    blood_summary_df = blood_df['SubjectId'].drop_duplicates()
    # get first treatment info:
    first_trt = original_blood_df[(original_blood_df['Visit'] == 'PRE') & (original_blood_df['TreatmentDate'].notna())]
    first_trt = first_trt[['SubjectId', 'TreatmentDate']]
    blood_summary_df = pd.merge(blood_summary_df, first_trt, on='SubjectId', how='left')
    # get t0 blood collection info:
    first_blood = blood_df[(blood_df['Visit'] == 'PRE') & (blood_df['BloodCollectionDate'].notna())]
    first_blood = first_blood[['SubjectId', 'BloodCollectionDate']]
    blood_summary_df = pd.merge(blood_summary_df, first_blood, on='SubjectId', how='left')
    # get progression info:
    blood_summary_df = get_progression(clin_dict, blood_summary_df)
    blood_summary_df.rename(columns={'TreatmentDate': 'FirstTreatmentDate', 'PFSDate': 'ProgressionDate',
                                     'BloodCollectionDate': 'T0Date', 'NEW_OSDateCurated': 'OSDate'}, inplace=True)

    # histogram of number of blood samples
    print("According to current NSCLC data from 24.12.23:")
    print(f"- The number of blood collections reported: {len(blood_df)}")
    print(f"- The number of patients with reported blood collections: {len(blood_df['SubjectId'].unique())}")
    sample_counts = blood_df['SubjectId'].value_counts()
    plt.figure(figsize=(10, 6))
    plt.hist(sample_counts, bins=range(1, sample_counts.max() + 2), align='left', edgecolor='black')
    plt.xlabel('Blood Sample Count', fontsize=14)
    plt.ylabel('Number of Patients', fontsize=14)
    plt.title('Sample Counts per Patient - Before Cleaning', fontsize=16)
    plt.grid(linestyle='--', alpha=0.7)
    plt.xticks(range(1, sample_counts.max() + 1), fontsize=12)
    plt.yticks(fontsize=12)
    plt.savefig('plots/sample_distribution.png')

    # new histogram with cleaned patients with less than two blood samples and no first treatment found
    # filter for no treatment or t0 dates
    ids_to_keep = blood_summary_df.loc[
        (blood_summary_df['FirstTreatmentDate'].notna()) & (blood_summary_df['T0Date'].notna()), 'SubjectId']
    filtered_blood_df = blood_df[blood_df['SubjectId'].isin(ids_to_keep)]
    # filter for at least two samples
    sample_counts_filtered = filtered_blood_df['SubjectId'].value_counts()
    sample_counts_filtered = sample_counts_filtered[sample_counts_filtered >= 2]
    filtered_blood_df = blood_df[blood_df['SubjectId'].isin(sample_counts_filtered.index)]
    print(f"- The number of blood collections reported after cleaning: {len(filtered_blood_df)}")
    print(
        f"- The number of patients with reported blood collections after cleaning: {len(filtered_blood_df['SubjectId'].unique())}")
    plt.figure(figsize=(10, 6))
    plt.hist(sample_counts_filtered, bins=range(2, sample_counts_filtered.max() + 2), align='left', edgecolor='black')
    plt.xlabel('Blood Sample Count', fontsize=14)
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
    blood_summary_df['IsTprogAlsoT0'] = False
    filtered_blood_df['Tnum'] = None

    blood_summary_df.set_index('SubjectId', inplace=True)
    ix = blood_summary_df.index.isin(filtered_blood_df['SubjectId'])
    blood_summary_df.loc[ix, 'PassedFilter'] = True

    # how many patients have progressed at all
    n = len(blood_summary_df[blood_summary_df['PassedFilter'] & blood_summary_df['ProgressionDate'].notna()])
    print(f"From the filtered data, the number of patients that have progressed are: {n}")
    n = len(blood_summary_df[blood_summary_df['PassedFilter'] & blood_summary_df['ProgressionDate'].isna()])
    print(f"From the filtered data, the number of patients that have not progressed at all are: {n}")

    # fill t0:
    ix = (filtered_blood_df['Visit'] == 'PRE') & filtered_blood_df['BloodCollectionDate'].notna()
    filtered_blood_df.loc[ix, 'Tnum'] = 0
    subject_with_multiple_t0 = filtered_blood_df[filtered_blood_df['Tnum'] == 0]['SubjectId'].duplicated(keep=False)
    # Check if there are any subjects with multiple T0:
    if subject_with_multiple_t0.any():
        subjects_with_multiple_rows = filtered_blood_df.loc[subject_with_multiple_t0, 'SubjectId'].unique()
        print("WARNING: Subjects with multiple rows with T0:", subjects_with_multiple_rows)

    # fill summary columns and #T:
    two_weeks = pd.Timedelta(days=14)
    month_and_half = pd.Timedelta(days=45)
    month = pd.Timedelta(days=30)
    filtered_blood_df['Duration'] = None
    for sub_id, sub_df in filtered_blood_df.groupby('SubjectId'):
        prog_date = blood_summary_df.at[sub_id, 'ProgressionDate']
        trt_date = blood_summary_df.at[sub_id, 'FirstTreatmentDate']
        # calculate t1:
        has_t1 = False
        count = 2
        for index, row in sub_df.iterrows():
            trt_difference = row['BloodCollectionDate'] - trt_date
            if two_weeks <= trt_difference <= month_and_half and not has_t1:
                has_t1 = True
                blood_summary_df.at[sub_id, 'HasT1'] = True
                blood_summary_df.at[sub_id, 'T1Date'] = row['BloodCollectionDate']
                filtered_blood_df.loc[index, 'Tnum'] = 1
                if row['BloodCollectionDate'] == blood_summary_df.at[sub_id, 'T0Date']:
                    print(f"WARNING: {sub_id} T0 == T1")
            if has_t1:
                break
        # calculate tprog:
        if pd.notna(prog_date):
            # progressed
            dates = sub_df['BloodCollectionDate'].values
            target_date = prog_date + pd.DateOffset(months=1)
            chosen_date = min(dates, key=lambda x: abs((x - target_date).days))
            difference = abs((target_date - chosen_date).days)
            if difference <= month.days:
                blood_summary_df.at[sub_id, 'HasTprog'] = True
                blood_summary_df.at[sub_id, 'TprogDate'] = chosen_date
                if has_t1 and chosen_date == blood_summary_df.at[sub_id, 'T1Date']:
                    blood_summary_df.at[sub_id, 'IsTprogAlsoT1'] = True
                if chosen_date == blood_summary_df.at[sub_id, 'T0Date']:
                    blood_summary_df.at[sub_id, 'IsTprogAlsoT0'] = True
                # calculate durations for dates before the Tprog:
                for index, row in sub_df.iterrows():
                    if row['BloodCollectionDate'] == chosen_date:
                        filtered_blood_df.loc[index, 'Tnum'] = 'PD'
                    elif row['BloodCollectionDate'] > chosen_date:
                        filtered_blood_df.loc[index, 'Tnum'] = '> PD'
                    else:
                        trt_difference = row['BloodCollectionDate'] - trt_date
                        filtered_blood_df.loc[index, 'Duration'] = trt_difference.days
                        x = filtered_blood_df.loc[index, 'Tnum']
                        if x == None:
                            filtered_blood_df.loc[index, 'Tnum'] = count
                            count = count + 1
            else:  # has progression but not tprog
                # calculate durations for dates before the progression:
                for index, row in sub_df.iterrows():
                    if row['BloodCollectionDate'] >= prog_date:
                        filtered_blood_df.loc[index, 'Tnum'] = ' >= PD'
                    else:
                        trt_difference = row['BloodCollectionDate'] - trt_date
                        filtered_blood_df.loc[index, 'Duration'] = trt_difference.days
                        x = filtered_blood_df.loc[index, 'Tnum']
                        if x == None:
                            filtered_blood_df.loc[index, 'Tnum'] = count
                            count = count + 1
        else:
            # calculate durations for all dates (no progression at all):
            sub_df['BloodCollectionDate'] = pd.to_datetime(sub_df['BloodCollectionDate'])
            filtered_blood_df.loc[sub_df.index, 'Duration'] = (sub_df['BloodCollectionDate'] - trt_date).dt.days
            for index, row in sub_df.iterrows():
                x = filtered_blood_df.loc[index, 'Tnum']
                if x == None:
                    filtered_blood_df.loc[index, 'Tnum'] = count
                    count = count + 1

    filtered_blood_df.to_excel('checking.xlsx')

    # from the patients that have not progressed
    print(f"- The number of patients that have not progressed and have t1: {sum(blood_summary_df.loc[blood_summary_df['ProgressionDate'].isna(), 'HasT1'])}")

    # see the number of patients with and without t progression / T1
    progression_patients = blood_summary_df[
        blood_summary_df['ProgressionDate'].notna() & blood_summary_df['PassedFilter']]
    progression_patients['Group'] = None
    progression_patients.loc[
        progression_patients['HasT1'] & ~progression_patients['HasTprog'], 'Group'] = 'Has T1 but not Tprog'
    progression_patients.loc[
        ~progression_patients['HasT1'] & progression_patients['HasTprog'], 'Group'] = 'Has Tprog but not T1'
    progression_patients.loc[progression_patients['HasT1'] & progression_patients['HasTprog'], 'Group'] = 'Has Both'
    progression_patients.loc[
        ~progression_patients['HasT1'] & ~progression_patients['HasTprog'], 'Group'] = 'Has Neither'

    group_order = ['Has Tprog but not T1', 'Has Both', 'Has T1 but not Tprog', 'Has Neither']
    # Count the number of patients in each group
    group_counts = progression_patients['Group'].value_counts()
    group_counts = group_counts.loc[group_order]
    print(group_counts)
    plt.figure(figsize=(10, 6))
    plt.bar(group_counts.index, group_counts, color=['blue', 'blue', 'orange', 'orange'])
    plt.xlabel('Patient Groups', fontsize=14)
    plt.ylabel('Number of Patients', fontsize=14)
    plt.title('Distribution of Patients with Progression By Group', fontsize=16)
    plt.grid(linestyle='--', alpha=0.7)
    plt.xticks(fontsize=12)
    plt.yticks(fontsize=12)
    plt.legend(handles=[plt.Rectangle((0, 0), 1, 1, color='orange', label='No Tprogression'),
                        plt.Rectangle((0, 0), 1, 1, color='blue', label='Have Tprogression')])
    plt.savefig('plots/progression_blood_sample_types_distribution.png')
    print(f"- The number of patient where the Tprogression == T1: {sum(progression_patients['IsTprogAlsoT1'])}")
    print(f"- The number of patient where the Tprogression == T0: {sum(progression_patients['IsTprogAlsoT0'])}")

    # calculate pfs durations:
    blood_summary_df['ProgressionDuration'] = None
    ix = blood_summary_df['ProgressionDate'].notna() | blood_summary_df['OSDate'].notna()
    blood_summary_df.loc[ix] = blood_summary_df.loc[ix].apply(get_progression_duration, axis=1)
    # calculate tprog durations:
    blood_summary_df['TprogDuration'] = None
    ix = blood_summary_df['HasTprog']
    blood_summary_df['TprogDate'] = pd.to_datetime(blood_summary_df['TprogDate'])
    blood_summary_df['FirstTreatmentDate'] = pd.to_datetime(blood_summary_df['FirstTreatmentDate'])
    blood_summary_df.loc[ix, 'TprogDuration'] = (
                blood_summary_df.loc[ix, 'TprogDate'] - blood_summary_df.loc[ix, 'FirstTreatmentDate']).dt.days
    # delta between distributions TPROG_D - PROG_D
    blood_summary_df['DurationDelta'] = None
    blood_summary_df.loc[ix, 'DurationDelta'] = (
                blood_summary_df.loc[ix, 'TprogDuration'] - blood_summary_df.loc[ix, 'ProgressionDuration'])
    # blood_summary_df[blood_summary_df['HasTprog'] & blood_summary_df['PassedFilter']].to_excel('with_tprog.xlsx')

    # do twice 1-Tprog patients with t1  2-Tprog patients withput t1:
    # 3 histograms:
    # tprog duration distibution
    # PFS duration distribution
    # the delta between them distribution
    # for tprog_group in ['with_Tprog_and_T1', 'with_Tprog_without_T1', 'all_Tprog']:
    for tprog_group in ['all_Tprog']:
        if tprog_group == 'all_Tprog':
            cond = blood_summary_df['HasTprog'] & blood_summary_df['PassedFilter']
        elif tprog_group == 'with_Tprog_and_T1':
            cond = blood_summary_df['HasTprog'] & blood_summary_df['HasT1'] & blood_summary_df['PassedFilter']
        else:
            cond = blood_summary_df['HasTprog'] & ~blood_summary_df['HasT1'] & blood_summary_df['PassedFilter']
        duration_df = blood_summary_df[cond]

        # Plot TprogDuration distribution
        counts_tprog = duration_df['TprogDuration'].value_counts()
        plt.figure(figsize=(10, 6))
        bins = range(0, int(max(counts_tprog.index)) + 31, 30)
        plt.hist(counts_tprog.index, bins=bins, weights=counts_tprog, align='left', edgecolor='black')
        plt.xlabel('Tprogression Duration (days)', fontsize=12)
        plt.ylabel('Number of Patients', fontsize=14)
        plt.title("Tprogression Duration Distribution", fontsize=16)
        plt.grid(linestyle='--', alpha=0.7)
        bin_centers = [bin_start + 15 for bin_start in bins[:-1]]
        xticks = [bins[0] - 15] + bin_centers
        plt.xticks(xticks, fontsize=6)
        plt.yticks(fontsize=12)
        plt.savefig(f"plots/{tprog_group}_Tprogression_duration_distribution.png")

        # Plot ProgressionDuration distribution
        counts_progression = duration_df['ProgressionDuration'].value_counts()
        plt.figure(figsize=(10, 6))
        bins = range(-30, int(max(counts_progression.index)) + 31, 30)
        plt.hist(counts_progression.index, bins=bins, weights=counts_progression, align='left', edgecolor='black')
        plt.xlabel('Progression Duration (days)', fontsize=12)
        plt.ylabel('Number of Patients', fontsize=14)
        plt.title('Progression Duration Distribution', fontsize=16)
        plt.grid(linestyle='--', alpha=0.7)
        bin_centers = [bin_start + 15 for bin_start in bins[:-1]]
        xticks = [bins[0] - 15] + bin_centers
        plt.xticks(xticks, fontsize=6)
        plt.yticks(fontsize=12)
        plt.savefig(f"plots/{tprog_group}_progression_duration_distribution.png")

        # Plot Delta durations distribution
        counts_delta = duration_df['DurationDelta'].value_counts()
        plt.figure(figsize=(10, 6))
        bins = range(int(min(counts_delta.index)), int(max(counts_delta.index)) + 31, 30)
        plt.hist(counts_delta.index, bins=bins, weights=counts_delta, align='left', edgecolor='black')
        plt.xlabel('Delta Tprog/Progression (days)', fontsize=12)
        plt.ylabel('Number of Patients', fontsize=14)
        plt.title('Delta of Durations distribution (Tprogression Duration - Progression Duration)', fontsize=16)
        plt.grid(linestyle='--', alpha=0.7)
        bin_centers = [bin_start + 15 for bin_start in bins[:-1]]
        xticks = [bins[0] - 15] + bin_centers
        plt.xticks(xticks, fontsize=10)
        plt.yticks(fontsize=12)
        plt.savefig(f"plots/{tprog_group}_delta_duration_distribution.png")

    # compare tprog duration with controls
    duration_df = blood_summary_df[blood_summary_df['HasTprog'] & blood_summary_df['PassedFilter']]
    counts_tprog = duration_df.loc[duration_df['TprogDuration'] > 0, 'TprogDuration'].value_counts()
    ix = filtered_blood_df['Duration'].notna() & (filtered_blood_df['Duration'] > 0) & (
                filtered_blood_df['Duration'] <= int(max(counts_tprog.index)))
    positive_control_counts = filtered_blood_df.loc[ix, 'Duration'].value_counts()
    plt.figure(figsize=(10, 6))
    bins = range(0, int(max(counts_tprog.index)) + 31, 30)
    plt.hist(positive_control_counts.index, bins=bins, label='Control', weights=positive_control_counts, align='left',
             edgecolor='black')
    plt.hist(counts_tprog.index, bins=bins, label='Tprogression', weights=counts_tprog, align='left', edgecolor='black')
    plt.xlabel('Duration (days)', fontsize=12)
    plt.ylabel('Number of Patients', fontsize=14)
    plt.title('Positive Durations Distribution', fontsize=16)
    plt.grid(linestyle='--', alpha=0.7)
    bin_centers = [bin_start + 15 for bin_start in bins[:-1]]
    xticks = [bins[0] - 15] + bin_centers
    plt.xticks(xticks, fontsize=6)
    plt.yticks(fontsize=12)
    plt.ylim(0, 90)
    plt.legend()
    plt.savefig(f"plots/tprog_control_duration_distribution.png")

    # look at the amount of patient with eligibility errors:
    eligibility_df = pd.read_excel('eligibility.xlsx')
    blood_summary_df = pd.merge(blood_summary_df, eligibility_df, on='SubjectId', how='left')
    blood_summary_df['IsEligible'] = False
    ix = blood_summary_df['Eligibility V3'].isna()
    blood_summary_df.loc[ix, 'IsEligible'] = True

    ix = blood_summary_df['PassedFilter']
    print(f"The number of patients eligible from cleaned data: {sum(blood_summary_df.loc[ix, 'IsEligible'])}")
    ix = blood_summary_df['PassedFilter'] & blood_summary_df['ProgressionDate'].notna()
    print(
        f"The number of patients eligible from cleaned data with progression: {sum(blood_summary_df.loc[ix, 'IsEligible'])}")
    ix = blood_summary_df['PassedFilter'] & blood_summary_df['ProgressionDate'].isna()
    print(
        f"The number of patients eligible from cleaned data without progression: {sum(blood_summary_df.loc[ix, 'IsEligible'])}")
    ix = blood_summary_df['PassedFilter'] & blood_summary_df['HasTprog']
    print(
        f"The number of patients eligible from cleaned data with Tprogression: {sum(blood_summary_df.loc[ix, 'IsEligible'])}")

    reasons = [
        "No T0 essay",
        "Prior chemo ended 1 months or less before treatment",
        "Received neither Mono/Combo/Chemo treatment",
        "T0 taken after treatment",
        "Blood collection too early (more than 2 weeks)",
        "No first treatment",
        "No second treatment",
        "Progression before second treatment",
        "Unknown ECOG",
        "ECOG >= 3",
        "Other malignancy",
        "Prior immunotherapy",
        "Stage is not 4 or 3C",
        "No consent",
        "Not first line/Unknown line"
    ]
    # make a df that for each reason count how many patients that passed the filter have it and export as excel
    reasons_count_df = pd.DataFrame({'Reason': reasons, 'Count': 0})
    # Count occurrences for each reason
    for i, reason in enumerate(reasons):
        reasons_count_df.at[i, 'Count'] = blood_summary_df.loc[ix, 'Eligibility V3'].str.contains(reason).sum()

    # Export the DataFrame to a CSV file
    reasons_count_df.to_csv('eligibility_reasons_count.csv', index=False)

    # how many patient have tn's and how many tn samples exist
    ix = filtered_blood_df['Tnum'].apply(lambda x: isinstance(x, int) and x >= 2)
    print(f"The number of Tn samples that exist is: {len(filtered_blood_df[ix])}")
    print(f"The number of patients that have at least one Tn sample (other than 0,1,PD): {len(filtered_blood_df.loc[ix, 'SubjectId'].unique())}")

