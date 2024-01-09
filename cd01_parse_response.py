# -*- coding: utf-8 -*-
"""
Created on Sat Jul  1 23:17:45 2023

@author: BenYellinOncohost
"""


import pandas as pd
pd.options.mode.chained_assignment = None  # default='warn'
from cd01_utils import viedoc_to_df, convert_to_date, fillna


def parse_response(clin_dict, first_treatment,
                   min_days_to_pfs = 50,
                   max_days_to_os = 50,
                   max_days_to_pd = 50,
                   form_dict = {'Response Evaluation':'REC',
                                'E.O.S.':'EOS',
                                'Status':'STAT',
                                'Unschedualed Visits':'UNS'},
                   parsing_dicts={'DiscontinuationReason':'Data_and_dicts/230725_discontinuation_reason_dict.csv',
                                  'DeathReason':'Data_and_Dicts/230723_death_reason_dict.csv'},
                   manual_curation={'Summary PFS':'ManualCuration/230719 eos_pfs_mismatch.csv'}):
    ''' ###### Response evaluation
    ## Forms: 'REC', 'EOS', 'STAT', 'UNS'
    ## Extract: OS, PFS, Last followup, death/treatment change reasons
    ## 'REC' - response evaluation. ORR, PFS, OS, Death reason
    ## 'REC' TBD: 
    ##   - Check if stable disease/remission was reported after progression. Check that treatment did not change - if so, change PFS
    ##   - Add recurence sites and numbers
    ## 'EOS' - End of study. PFS, OS, stop/change reason
    ## 'UNS' - Unscedualed visits. used to extract last followup date
    ## TBD:
    ##   - Create report for clinical team for 'REC' curation
    ##   - Create report for clinical team  for mismatch between EOS  for PFS and OS
    ##   - Check StillAlive vs OS in all relevant forms (EOS, REC?,STAT?)
    ##   - last treatment date
    ##   - Add status form to analysis?
    
    '''
    
    discont_reason_dict = pd.read_csv(parsing_dicts['DiscontinuationReason']).set_index('DiscontinuationReason').Parsing.to_dict()
    death_reason_dict = pd.read_csv(parsing_dicts['DeathReason'],encoding='latin-1').set_index('DeathReason').Parsing.to_dict()
    
    first_treatment =  first_treatment.copy()
    first_treatment.name = 'FirstTreatmentDate'
    
    ###### 'REC' - Tumor evaluation
    ## 
    rec_df = viedoc_to_df(clin_dict['REC'])
    rec_df = rec_df.join(first_treatment)
    rec_df = rec_df.reset_index()
    rec_df['EventDate'] = convert_to_date(rec_df['Event date'])
    rec_df['ORRDate'] = convert_to_date(rec_df['Date ORR was completed:'])
    rec_df['RecProgDate'] = convert_to_date(rec_df['Date of Recurrence/Progression:'], nk_day='max')
    rec_df['PFSDate'] = convert_to_date(fillna(rec_df,['PFS Date','PFS Date.1']))
    rec_df['OSDate'] = convert_to_date(fillna(rec_df,['Date of Death - OS' ,'Date of Death - OS.1']))
    rec_df['OSDuration'] = (rec_df.OSDate-rec_df.FirstTreatmentDate).dt.days
    rec_df['LastTreatmentDate'] = convert_to_date(fillna(rec_df,['Date of last treatment given', 'Date of last treatment given.1']))
    rec_df['DeathReasonText'] = fillna(rec_df,['Provide primary reason for Death', 'Provide primary reason for Death.1'])    
    rec_df['AutoParsingNotes'] = ''
    rec_df = rec_df.rename(columns={'Still Alive ALIVE':'StillAlive',
                                    'Overall Response Rate:':'ORR',
                                    'Subject form sequence number':'EventSequenceNumber',
                                    'ORR Evaluation Scale used:':'ORREvaluationScale',
                                    'Provide the Assessment Method:':'ORREvaluationMethod',
                                    'Number of Site of Recurrence:':'RecurrenceSiteNumber',})
   
    ## Parse death reasons
    death_reason_text = rec_df.DeathReasonText.str.lower().str.strip(' .')
    rec_df['DeathReason'] = death_reason_text.map(death_reason_dict)
    
    reason_report = pd.DataFrame({'Text':death_reason_dict.keys(),'Parsing':death_reason_dict.values()})
    reason_report['Type'] = 'Death'
    reason_report['Form'] = 'Dictionary'
    
    aux_reason_report = pd.DataFrame({'Text':discont_reason_dict.keys(),'Parsing':discont_reason_dict.values()})
    aux_reason_report['Type'] = 'Discontinuation'
    aux_reason_report['Form'] = 'Dictionary'  
    reason_report = pd.concat([reason_report, aux_reason_report])
      
    aux_reason_report = pd.DataFrame({'Text':death_reason_text,'Parsing':rec_df['DeathReason']})
    aux_reason_report['Type'] = 'Death'
    aux_reason_report['Form'] = 'REC'  
    reason_report = pd.concat([reason_report, aux_reason_report])
    
    #### OS
    rec_os = rec_df.loc[rec_df.OSDate.notna(),['SubjectId','OSDate', 'OSDuration','DeathReasonText','StillAlive']]
    rec_os = rec_os.set_index('SubjectId')

    ## OS checks:
    # negative OS duration 
    # ix = rec_df.OSDuration<0
    # msg = 'Nagative OS Date,'
    # rec_df.AutoParsingNotes = rec_df.AutoParsingNotes + ix.map({False:'',True:msg})
   
    #### PFS
    ix = rec_df.ORR == 'Progressive Disease (PD)'
    rec_df.loc[ix,'PFSDateCurated'] = fillna(rec_df[ix],['PFSDate','RecProgDate','ORRDate','EventDate'], warn=False)
    rec_df['PFSDuration'] = (rec_df.PFSDateCurated-rec_df.FirstTreatmentDate).dt.days
    rec_pfs = rec_df[['SubjectId', 'ORR','FirstTreatmentDate','EventDate','ORRDate','RecProgDate','PFSDate','PFSDateCurated','PFSDuration']]
    rec_pfs = rec_pfs[rec_pfs.ORR == 'Progressive Disease (PD)']
    rec_pfs = rec_pfs.drop_duplicates(['SubjectId','PFSDateCurated'])
    rec_pfs = rec_pfs.loc[rec_pfs.groupby('SubjectId').PFSDateCurated.idxmin()]
    rec_pfs = rec_pfs.set_index('SubjectId')
    
    ## PFS checks
    # PD, No PFS date
    # ix = rec_df[['PFSDate','RecProgDate','ORRDate']].isna().sum(axis=1) == 3
    # ix = ix&(rec_df.ORR == 'Progressive Disease (PD)')
    # msg = 'PD - but no PFS date/RecProg date/ORR date,'
    # rec_df.AutoParsingNotes = rec_df.AutoParsingNotes + ix.map({False:'',True:msg})
 
    # No PD, have PFS date
    # ix = rec_df[['PFSDate','RecProgDate']].notna().sum(axis=1) > 0
    # ix = ix&(rec_df.ORR!='Progressive Disease (PD)')
    # msg = 'No PD - but have PFS date/RecProg date,'
    # rec_df.AutoParsingNotes = rec_df.AutoParsingNotes + ix.map({False:'',True:msg})
    
    # Negative PFS
    # ix = rec_df.PFSDuration < 0
    # msg = 'Negative PFS Duration,'
    # rec_df.AutoParsingNotes = rec_df.AutoParsingNotes + ix.map({False:'',True:msg})
 
    # Non matching recprogdate pfsdate
    # ix = rec_df.RecProgDate != rec_df.PFSDate
    # ix = ix&rec_df.RecProgDate.notna()&rec_df.PFSDate.notna()
    # msg = 'Rec/Prog date dont match PFS Date,'
    # rec_df.AutoParsingNotes = rec_df.AutoParsingNotes + ix.map({False:'',True:msg})
 
    # TBD: PFS after OS?
    
    #### Last followup date - max date
    date_cols = ['EventDate', 'ORRDate', 'RecProgDate', 'PFSDate',
                 'OSDate', 'LastTreatmentDate']
    rec_df['MaxDate'] = rec_df[date_cols].max(axis=1)
    rec_lastFU = rec_df[['SubjectId','MaxDate']+date_cols]
    rec_lastFU = rec_lastFU.loc[rec_lastFU.groupby('SubjectId').EventDate.idxmax()]
    rec_lastFU = rec_lastFU.set_index('SubjectId').MaxDate
    #### TBD: Last treatment
    #### TBD: still alive
    
    
    #### Organise
    rec_df.AutoParsingNotes = rec_df.AutoParsingNotes.str.strip(' ,').replace('',None)
    cols = ['SubjectId', 'Site', 'Indication', 'FirstTreatmentDate',
            'Event Id', 'EventSequenceNumber', 'EventDate',
            'ORR', 'ORRDate', 'RecProgDate', 'PFSDate', 'PFSDateCurated', 'PFSDuration',
            'StillAlive', 'OSDate', 'OSDuration', 'LastTreatmentDate', 'DeathReasonText',
            'ORREvaluationScale', 'ORREvaluationMethod', 'Comments', 'AutoParsingNotes'
            ]
    rec_df = rec_df[cols]


    ###### 'EOS' - End of study df   
    eos_df = viedoc_to_df(clin_dict['EOS']) 
    
    eos_df = eos_df.rename(columns = {
        'Event date':'EOSEventDate',
        'Primary reason for Discontinuation':'DiscontinuationReasonText', 
        'Other, please specify:':'Other1', 'Please specify':'Other2',
        'PFS Date':'PFSDate',
        'Date of Death -Overall survival (OS)':'OSDate',
        'Still Alive ALIVE':'StillAliveAtEOS',
        'Provide primary reason for Death:':'DeathReasonText',
        'Date of last treatment given':'LastTreatmentDate',
        'Completion/Discontinuation Status':'EOSStatus',
        'Date of study completion/discontinuation':'EOSDate',
        'Date of Last Contact':'LastContactDate'})
    eos_df['AutoParsingNotes'] = ''

    #### merge and parse text columns
    other_reasons = fillna(eos_df,['Other1','Other2'])
    eos_df.loc[other_reasons.notna(),'DiscontinuationReasonText'] = None
    eos_df['DiscontinuationReasonText'] = fillna(eos_df,['DiscontinuationReasonText', 'Other1','Other2'])
    
    discont_reason_text = eos_df['DiscontinuationReasonText'].str.lower().str.strip(' .')
    eos_df['DiscontinuationReason'] = discont_reason_text.map(discont_reason_dict)
    
    aux_reason_report = pd.DataFrame({'Text':discont_reason_text,'Parsing':eos_df['DiscontinuationReason']})
    aux_reason_report['Type'] = 'Discontinuation'
    aux_reason_report['Form'] = 'EOS'
    reason_report = pd.concat([reason_report,aux_reason_report])
    
    death_reason_text = eos_df['DeathReasonText'].str.lower().str.strip(' .')
    eos_df['DeathReason'] = death_reason_text.map(death_reason_dict)
    
    aux_reason_report = pd.DataFrame({'Text':death_reason_text,'Parsing':eos_df['DeathReason']})
    aux_reason_report['Type'] = 'Death'
    aux_reason_report['Form'] = 'EOS'
    reason_report = pd.concat([reason_report,aux_reason_report])
    
   
    #### Calculate dates
    ## Calculate duration
    eos_df = eos_df.join(first_treatment)
    date_cols = ['EOSEventDate','EOSDate','PFSDate','OSDate','LastTreatmentDate','LastContactDate']
    for col in date_cols:
        eos_df[col] = convert_to_date(eos_df[col])
        eos_df[col[:-4]+'Duration'] = (eos_df[col]-eos_df.FirstTreatmentDate).dt.days
        ix = eos_df[col[:-4]+'Duration']<0
        # if ix.sum()>0:
        #     msg = f'Negative {col[:-4]} Duration,'
        #     eos_df.AutoParsingNotes = eos_df.AutoParsingNotes + ix.map({False:'',True:msg})
            
    ## Last followup date - max date
    eos_df['EOSMaxDate'] = eos_df[date_cols].max(axis=1)       
    eos_df['EOSMaxDuration'] =(eos_df.EOSMaxDate-eos_df.FirstTreatmentDate).dt.days 
     
    # PFS after OS
    # ix = (eos_df['OSDuration']-eos_df['PFSDuration'])<0
    # msg = 'PFS after OS,'
    # eos_df.AutoParsingNotes = eos_df.AutoParsingNotes + ix.map({False:'',True:msg})
    
    # Available updates after last followup
    # ix = eos_df['LastContactDuration']<eos_df['EOSMaxDuration']
    # msg = 'Available updates after last contact date,'
    # eos_df.AutoParsingNotes = eos_df.AutoParsingNotes + ix.map({False:'',True:msg})
    
    
    # # Early PFS - Not relevant for eos form. moved to summary
    # ix = eos_df.PFSDuration.between(0,min_days_to_pfs)
    # ix = ix&(eos_df.OSDuration.isna()|(eos_df.OSDuration > eos_df.PFSDuration+max_days_to_os))
    # msg = f'PFS Duration is less then {min_days_to_pfs} days (without OS in the next {max_days_to_os} days),'
    # eos_df.AutoParsingNotes = eos_df.AutoParsingNotes + ix.map({False:'',True:msg})   
    
    
    #### Organise 
    eos_df.AutoParsingNotes = eos_df.AutoParsingNotes.str.strip(' ,').replace('',None)
    cols = ['Site', 'Indication', 'Design version', 'FirstTreatmentDate',
            'EOSEventDate',  'EOSEventDuration', 'EOSDate', 'EOSDuration',
            'LastContactDate', 'LastContactDuration', 
            'LastTreatmentDate',  'LastTreatmentDuration',
            'PFSDate', 'PFSDuration', 'OSDate', 'OSDuration',
            'EOSMaxDate','EOSMaxDuration',
            'EOSStatus','StillAliveAtEOS',
            'DiscontinuationReasonText', 'DiscontinuationReason',
            'DeathReasonText', 'DeathReason', 
            'AutoParsingNotes']
    
    eos_df = eos_df[cols]
    
        
    ###### Unschdualed visits
    uns_df = viedoc_to_df(clin_dict['UNS'])
    uns_df = uns_df.join(first_treatment)
    uns_df = uns_df.reset_index()
    uns_df['EventDate'] = convert_to_date(uns_df['Event date'])
    uns_df = uns_df.loc[uns_df.groupby('SubjectId').EventDate.idxmax()]
    uns_lastFU = uns_df.set_index('SubjectId').EventDate
     
    
    ###### merge response data
    #### create summary data frame
    summary_df = viedoc_to_df(clin_dict['DM'])[['Site', 'Indication']]
    summary_df = summary_df.join(first_treatment)
    cols = ['EOSStatus', 'EOSDate', 'EOSDuration',
            'EOSMaxDate', 'EOSMaxDuration',
            'LastTreatmentDate',  'LastTreatmentDuration',
            'DiscontinuationReasonText', 'DiscontinuationReason']
    summary_df = summary_df.join(eos_df[cols])
    summary_df.EOSStatus = summary_df.EOSStatus.fillna('Ongoing')
    summary_df.loc[summary_df.Indication=='HEALTHY','EOSStatus'] = 'Healthy'
    summary_df['AutoParsingNotes'] = ''
    
    # ix = pd.Series(~eos_df.index.isin(summary_df.index), index=eos_df.index)
    # msg = 'Not available in demographic data (DM form),'
    # eos_df.AutoParsingNotes = eos_df.AutoParsingNotes + ix.map({False:'',True:msg})
    #
    # ix = summary_df.FirstTreatmentDate.isna()
    # msg = 'Missing first treatment date'
    # summary_df.AutoParsingNotes = summary_df.AutoParsingNotes + ix.map({False:'',True:msg})
    
    
    #### OS    
    ## Date
    summary_df['OSDate_REC'] = rec_os['OSDate']
    summary_df['OSDate_EOS'] = eos_df['OSDate']
    summary_df['OSDateCurated'] = summary_df.OSDate_EOS.fillna(summary_df.OSDate_REC)
    summary_df['OSDuration'] = (summary_df.OSDateCurated-summary_df.FirstTreatmentDate).dt.days 
    ix = (summary_df['OSDate_EOS'] != summary_df['OSDate_REC'])&summary_df['OSDate_REC'].notna()&summary_df['OSDate_EOS'].notna()
    msg = 'exists an EOS OS date that does not match a REC OS date,'
    summary_df.AutoParsingNotes = summary_df.AutoParsingNotes + ix.map({False:'',True:msg})
    
    ## Reason
    summary_df['DeathReason_REC'] = rec_os['DeathReasonText']
    summary_df['DeathReason_EOS'] = eos_df['DeathReasonText']
    summary_df['DeathReasonText'] = summary_df.DeathReason_EOS.fillna(summary_df.DeathReason_REC)
    death_reason_text = summary_df.DeathReasonText.str.lower().str.strip(' .')
    summary_df['DeathReason'] = death_reason_text.map(death_reason_dict)
    # TBD: reasons mismatch warning 
    
    ## Event
    summary_df['OSEvent'] = summary_df['OSDateCurated'].notna().astype(int)
    
    
    #### PFS   
    ## Date
    summary_df['PFSOrigin'] = None
    summary_df['PFSDate_REC'] = rec_pfs['PFSDateCurated']
    summary_df['PFSDate_EOS'] = eos_df['PFSDate']
    summary_df['PFSDateCurated'] = summary_df['PFSDate_EOS']
    summary_df.loc[summary_df['PFSDateCurated'].notna(), 'PFSOrigin'] = 'from EOS'
    summary_df['PFSDateCurated'] = summary_df['PFSDateCurated'].fillna(summary_df.PFSDate_REC)
    mask = summary_df['PFSDateCurated'].notna() & summary_df['PFSOrigin'].isna()
    summary_df.loc[mask, 'PFSOrigin'] = 'from REC'
    ix = (summary_df['PFSDate_EOS'] != summary_df['PFSDate_REC'])&summary_df['PFSDate_REC'].notna()&summary_df['PFSDate_EOS'].notna()
    msg = ' Exists an EOS PFS date that does not match a REC PFS date,'
    summary_df.AutoParsingNotes = summary_df.AutoParsingNotes + ix.map({False:'',True:msg})

    ## Date Manual updates
    man_cur = pd.read_csv(manual_curation['Summary PFS']).set_index('SubjectId')
    man_cur.PFS_ClinicalTeam = convert_to_date(man_cur.PFS_ClinicalTeam)
    ix = summary_df.index.isin(man_cur.index)
    summary_df['ManualCuration'] = ix
    summary_df.loc[ix,'PFSDateCurated'] = man_cur.PFS_ClinicalTeam
    msg = 'Manual PFS curation by ' + man_cur.CurationPersonal + ' at ' + man_cur.CurationDate +','
    summary_df['PFSAutoParsingNotes'] = ''
    summary_df.loc[ix,'PFSAutoParsingNotes'] = summary_df.loc[ix,'PFSAutoParsingNotes'] + msg
    mask = summary_df['PFSAutoParsingNotes'] == ''
    summary_df.loc[mask, 'PFSAutoParsingNotes'] = summary_df.loc[mask, 'PFSOrigin'].fillna('')
    summary_df['PFSDuration'] = (summary_df.PFSDateCurated-summary_df.FirstTreatmentDate).dt.days 

    ## Early PFS     
    ix_early = summary_df.PFSDuration.between(0,min_days_to_pfs)
    # find if progressive disease reported later
    ix = summary_df.PFSDate_EOS.isna()
    ix = ix&(~summary_df.index.isin(man_cur.index))
    ix = ix&summary_df['PFSDate_REC'].notna()
    aux_df = rec_df[rec_df.SubjectId.isin(ix.index[ix])]
    aux_df = aux_df[aux_df.ORR=='Progressive Disease (PD)']
    aux_df = aux_df.set_index('SubjectId')
    aux_df = aux_df.join(summary_df.PFSDate_REC)
    aux_df = aux_df.reset_index()
    aux_df['DaysToNextPD'] =  (aux_df.PFSDateCurated-aux_df.PFSDate_REC).dt.days
    aux_df['DaysToNextPD'] =  aux_df['DaysToNextPD'].between(0,max_days_to_pd)
    ix_next_pd = summary_df.index.isin(aux_df.SubjectId)
    # find if have os date reported later
    ix_next_os = (summary_df.OSDuration-summary_df.PFSDuration) <= max_days_to_os
    
    # mark early PFS
    #return  summary_df, ix_early,ix_next_pd,ix_next_os
    # ix = ix_early&(~ix_next_pd)&(~ix_next_os)
    # msg = f'PFS less then {min_days_to_pfs} days '
    # msg += f'with no OS in the next {max_days_to_os} days '
    # msg += f'and no PD in the next {max_days_to_pd} days'
    # summary_df.AutoParsingNotes = summary_df.AutoParsingNotes + ix.map({False:'',True:msg})
    

    #### Reasons: TBD. death and discontinuation reason from dicts

    
    #### LastFU - Last Followup
    summary_df['LastFUDate_REC'] = rec_lastFU
    summary_df['LastFUDate_EOS'] = eos_df['EOSMaxDate']
    summary_df['LastFUDate_UNS'] = uns_lastFU
    summary_df['LastFUDateCurated'] = summary_df[['LastFUDate_REC','LastFUDate_EOS','LastFUDate_UNS']].max(axis=1)
    summary_df['LastFUDuration'] = (summary_df.LastFUDateCurated-summary_df.FirstTreatmentDate).dt.days

    
    #### Organise summary
    summary_df.AutoParsingNotes = summary_df.AutoParsingNotes.str.strip(' ,').replace('',None)
    cols = ['Site', 'Indication', 'FirstTreatmentDate',
            'PFSDate_REC', 'PFSDate_EOS', 'PFSDateCurated', 'PFSDuration', 
            'OSDate_REC', 'OSDate_EOS', 'OSDateCurated', 'OSEvent', 'OSDuration', 
            'LastFUDate_REC', 'LastFUDate_EOS', 'LastFUDate_UNS', 'LastFUDateCurated', 'LastFUDuration',
            'EOSStatus', 'EOSDate', 'EOSDuration', 'EOSMaxDate', 'EOSMaxDuration',
            'LastTreatmentDate', 'LastTreatmentDuration',
            'DiscontinuationReasonText', 'DiscontinuationReason',
            'DeathReason_REC', 'DeathReason_EOS', 'DeathReasonText', 'DeathReason',
            'AutoParsingNotes', 'PFSAutoParsingNotes']
    summary_df =summary_df[cols]
    
    
    #### Organise parsing report
    reason_report = reason_report[reason_report.Text.notna()]
    reason_report.Form = pd.Categorical(reason_report.Form, ordered=True, categories=['Dictionary','EOS','REC'])
    reason_report = reason_report.sort_values('Form')
    reason_report = reason_report.drop_duplicates('Text',keep='first')
 
    cols = ['Form','Type','Text','Parsing']
    reason_report = reason_report[cols]
    
    ###### Return result
    ret_dict = {'Summary':summary_df,
                'Response Evaluation':rec_df,
                'E.O.S.':eos_df,
                'Parsing Report': reason_report}
    return ret_dict



if __name__ == "__main__":   
    clin_dict = pd.read_excel('Input/OncoHost_20231204_125302.xlsx', sheet_name=None)
    blood_df = viedoc_to_df(clin_dict['BLOOD'])
    blood_df = blood_df.rename(columns = {'Event Id':'Visit',
                                          'Blood Collection Date:':'BloodCollectionDate',
                                          'Treatment Date:':'TreatmentDate',
                                          'Blood Collection Time:':'BloodCollectionTime',
                                          'End Timefor Plasma Preparation Procedure:':'EndPrepTime'})
    first_treatment = convert_to_date(blood_df.TreatmentDate[blood_df.Visit=='PRE'])
    df_dict = parse_response(clin_dict,first_treatment)
    writer = pd.ExcelWriter("20231204_response_report.xlsx", engine="xlsxwriter")
    for sheet_name, aux_df in df_dict.items():
        aux_df.to_excel(writer, sheet_name=sheet_name)
    writer.close()

    
    
    
