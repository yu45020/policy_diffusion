from __future__ import division
import numpy as np
from numba import jit
import itertools
import time
import matplotlib.pyplot as plt
import sys
import abc
import json
import pickle
from tika import parser
import urllib2
import urllib
from urllib import urlopen
import re
import pandas as pd
from sklearn.decomposition import PCA
from fast_alignment import *    
from CleanText import clean_text_for_alignment, clean_text_for_query
from compiler.ast import flatten
from elasticsearch import Elasticsearch
import re
import csv


#TODO: incorporate plotting into grid code; not sure how to do this in way that works for all algorithms

class Experiment():

    #TODO: how to include parameters for the algorithms in here
    #use keyword arguments??
    def __init__(self, bills ={}, algorithm=None, results = {}, grid = {}):
    	self.bills = bills
    	self.algorithm = algorithm
        if bills == {}:
            self.scores = None
        else:
    	   self.scores = np.zeros((max(self.bills.keys())+1, max(self.bills.keys())+1))
    	self.results = {}
        self.grid = {}


    def evaluate(self):
        self.evaluate_algorithm(self.bills)

        self.plot_scores(self.scores, self.bills) 

        return self.scores, self.results


    def evaluate_algorithm(self, match_score = 3, mismatch_score = -1, gap_score = -2):
        '''
        args:
            matches: dictionary with field corresponding to text and match groups

        returns:
            matrix with scores between all pairs and a dictionary with information
        '''
        for i in self.bills.keys():
            for j in self.bills.keys():  
                if i != j:              

                    if self.bills[i] == {} or self.bills[j] == {}:
                        continue

                    if bills[i]['text'] == '' or bills[j]['text'] == '':
                        continue

                    text1 = self._prepare_text_left(bills[i]['text'], bills[i]['state'])
                    text2 = self._prepare_text_right(bills[j]['text'], bills[j]['state'])

                    # Create sequences to be aligned.
                    f = self.algorithm(text1, text2)
                    f.align(match_score, mismatch_score, gap_score)

                    self.scores[i,j] = self._get_score(f)

                    self.results[(i,j)] ={}
                    self.results[(i,j)]['alignments'] = f.alignments
                    self.results[(i,j)]['score'] = self._get_score(f)
                    self.results[(i,j)]['match'] = (bills[i]['match'] == bills[j]['match'])
                    self.results[(i,j)]['diff'] = [self._diff(alignment) for alignment in f.alignments]
                    self.results[(i,j)]['features'] = [self._alignment_features(a[1],a[2]) for a in f.alignments]

                    print 'i: ' + str(i) + ', j: ' + str(j) + ' score: ' + str(f.alignments[0][0])

        return self.scores, self.results


    def grid_search(self, match_scores = [2,3,4,5], mismatch_scores = [-1,-2,-3,-4,-5], gap_scores = [-1,-2,-3,-4,-5]):
        
        for match_score in match_scores:
            for mismatch_score in mismatch_scores:
                for gap_score in gap_scores:

                    print 'running model: match_score {0} mismatch_score {1} gap_score {2}'.format(match_score, mismatch_score, gap_score)

                    self.grid[(match_score, mismatch_score, gap_score)] = {}
                    self.evaluate_algorithm(bills, match_score, mismatch_score, gap_score)
                    self.grid[(match_score, mismatch_score, gap_score)]['results'] = self.results
                    self.grid[(match_score, mismatch_score, gap_score)]['scores'] = self.scores

        return self.grid

    def save(self, name):
        with open('../data/{0}.p'.format(name), 'wb') as fp:
            pickle.dump(self, fp)

    @abc.abstractmethod
    def _prepare_text_left(self):
    	pass


    @abc.abstractmethod
    def _prepare_text_right(self):
        pass


    @abc.abstractmethod
    def _get_score(self, alignment_alg):
        pass

    #alignment feature methods
    def _alignment_features(self,left, right):
        '''
        This function takes as input two alignments and produce features of these
        '''
        return alignment_features(left, right)


    def inspect_alignments(self, match_type = 0, start_score = 'max'):
        '''
            match_type is 0 if you want to inspect non-matches
            and 1 if you want to inspect matches
        '''
        alignments = [(value['score'], value['alignments'], key)  for key, value in self.results.items() if value['match'] == match_type]
        sorted_alignments = sorted(alignments, key=lambda tup: tup[0], reverse = True)

        if start_score == 'max':
            for total_score, alignments, key in sorted_alignments:
                for score, left, right in alignments:
                    for i in range(len(left)):
                        print left[i], right[i]

                    print 'alignment_score: ', score

                print 'total_alignments_score: ', total_score
                print 'key: ', key
                print '\n'

                raw_input("Press Enter to continue...")
        else:
            for total_score, alignments, key in sorted_alignments:
                if total_score > start_score:
                    pass
                else:
                    for score, left, right in alignments:
                        for i in range(len(left)):

                            print left[i], right[i]

                        print 'alignment_score: ', score

                    print 'total_alignments_score: ', total_score
                    print 'key: ', key
                    print '\n'


                raw_input("Press Enter to continue...")


    #plotting functions
    def plot_scores(self):

        matchScores = []
        nonMatchScores = []

        for i in self.bills.keys():
            for j in self.bills.keys():

                if self.scores[i,j] == 0:
                    #ignore if score zero because url is broken
                    pass
                elif i < j and self.bills[i]['match'] == self.bills[j]['match']:
                    matchScores.append(min(self.scores[i,j],200))
                else:
                    nonMatchScores.append(min(self.scores[i,j],200))

        bins = np.linspace(min(nonMatchScores + matchScores), max(nonMatchScores + matchScores), 100)
        plt.hist(nonMatchScores, bins, alpha=0.5, label='Non-Matches')
        plt.hist(matchScores, bins, alpha=0.5, label='Matches')
        plt.legend(loc='upper right')
        plt.xlabel('Alignment Score')
        plt.ylabel('Number of Bill Pairs')
        plt.title('Distribution of Alignment Scores')
        plt.show()

        #make boxplot
        data_to_plot = [matchScores, nonMatchScores]
        fig = plt.figure(1, figsize=(9, 6))
        ax = fig.add_subplot(111)
        bp = ax.boxplot(data_to_plot)
        ax.set_xticklabels(['Match Scores', 'Non-Match Scores'])
        fig.show()


    def low_rank_plot(self):

        #convert dictionary to matrix
        matches = [[value for key, value in values['features'].items()] \
            for keys, values in self.results.items() if values['match'] == 1]

        non_matches = [[value for key, value in values['features'].items()] \
            for keys, values in self.results.items() if values['match'] == 0]

        #matches from 0 to match_index
        match_index = len(matches)

        data = np.array(matches + non_matches)

        sklearn_pca = PCA(n_components=2)
        sklearn_transf = sklearn_pca.fit_transform(data)

        #plot data
        fig = plt.figure()
        ax1 = fig.add_subplot(111)
        plt.plot(sklearn_transf[:match_index,0],sklearn_transf[:match_index,1], 
                 'o', markersize=7, color='blue', alpha=0.5, label='matches')
        plt.plot(sklearn_transf[match_index:,0], sklearn_transf[match_index:,1], 
                 '^', markersize=7, color='red', alpha=0.5, label='non-matches')
        plt.xlim([-50,1000])
        plt.ylim([-500,500])
        plt.legend(loc='upper left');
        plt.show()


    ############################################################
    ##alignments utils
    def _diff(self, alignment):
        a = alignment[1]
        b = alignment[2]
        length = min(len(alignment[1]), len(alignment[2]))

        diff = []
        for i in range(length):
            if a[i] == b[i] or a[i] == '-' or b[i] == '-':
                continue
            else:
                diff.append((a[i], b[i]))

        return diff


class DocExperiment(Experiment):

    def _prepare_text_left(self, text, state):

        text = clean_text_for_query(text, state)

        return text.split()


    def _prepare_text_right(self, text, state):

        text = clean_text_for_query(text, state)

        return text.split()


    def _get_score(self, alignment_alg):
        return alignment_alg.alignments[0][0]


class SectionExperiment(Experiment):

    def _prepare_text_left(self, text, state):

        text = clean_text_for_alignment(text, state)

        return map(lambda x: x.split(), text)


    def _prepare_text_right(self, text, state):

        text = clean_text_for_alignment(text, state)

        return flatten(map(lambda x: x.split(), text))


    def _get_score(self, alignment_alg):

        scores = [score for score, left, right in alignment_alg.alignments]

        return sum(scores)

############################################################
##helper function
def alignment_features(left, right):
    '''
    This function takes as input two alignments and produce features of these
    '''
    #alignment features
    features = {}
    features['length'] = len(left)
    features['num_gaps_l'] = 0
    features['num_gaps_r'] = 0
    features['num_mismatches'] = 0
    features['num_matches'] = 0
    features['avg_gap_length_l'] = []
    features['avg_gap_length_r'] = []
    features['avg_consec_match_length'] = []

    #helper variables
    prev_gap_l = False
    prev_gap_r = False
    prev_match = False
    for i in range(len(left)):
        # print 'i: ', i
        # print 'features: ', features
        if left[i] == '-':
            features['num_gaps_l'] += 1
            if not prev_gap_l:
                features['avg_gap_length_l'].append(1)
                prev_gap_l = True
            else:
                features['avg_gap_length_l'][-1] += 1
        else:
            prev_gap_l = False
        if right[i] == '-':
            features['num_gaps_r'] += 1
            if not prev_gap_r:
                features['avg_gap_length_r'].append(1)
                prev_gap_r = True
            else:
                features['avg_gap_length_r'][-1] += 1
        else:
            prev_gap_r = False
        if left[i] != '-' and right[i] != '-':
            if left[i] != right[i]:
                features['num_mismatches'] += 1
            elif left[i] == right[i]:
                features['num_matches'] += 1
                if not prev_match:
                    features['avg_consec_match_length'].append(1)
                    prev_match = True
                else:
                    features['avg_consec_match_length'][-1] += 1
        if left[i] != right[i]:
            prev_match = False

    if features['avg_gap_length_l'] != []:
        features['avg_gap_length_l'] = np.mean(features['avg_gap_length_l'])
    else:
        features['avg_gap_length_l'] = 0
    if features['avg_gap_length_r'] != []:
        features['avg_gap_length_r'] = np.mean(features['avg_gap_length_r'])
    else:
        features['avg_gap_length_r'] = 0
    if features['avg_consec_match_length'] != []:
        features['avg_consec_match_length'] = np.mean(features['avg_consec_match_length'])
    else:
        features['avg_consec_match_length'] = 0

    return features

#good test case: results[(21,22)]
def test_alignment_features():

    def true_features(length, num_gaps_l, num_gaps_r, num_mismatches, 
                        num_matches, avg_gap_length_l, avg_gap_length_r,
                        avg_consec_match_length):
        truth = {}
        truth['length'] = length
        truth['num_gaps_l'] = num_gaps_l
        truth['num_gaps_r'] = num_gaps_r
        truth['num_mismatches'] = num_mismatches
        truth['num_matches'] = num_matches
        truth['avg_gap_length_l'] = avg_gap_length_l
        truth['avg_gap_length_r'] = avg_gap_length_r
        truth['avg_consec_match_length'] = avg_consec_match_length

        return truth

    def check_features_truth(truth, features):
        for field in features.keys():
            if features[field] != truth[field]:
                print field + ' is inconsistent'


    a1 = range(1,10) + ['-', '-'] + range(12,15)
    a2 = range(1,4) + ['-', '-', 7] + range(7,15)

    features = alignment_features(a1, a2)
    truth = true_features(14,2,2,1,9,2,2,3)

    print 'first test: '
    check_features_truth(truth, features)

    b1 = range(1,10)
    b2 = ['-','-',3,5,6,7, '-', '-', 9]
    features = alignment_features(b1, b2)
    truth = true_features(9,0,4,3,2,0,2,1)

    print 'second test: '
    check_features_truth(truth, features)



############################################################
##data creating, saving, and loading
def create_bills(ls):
    '''
    args:
        ls: list of lists of urls that correspond to matches

    returns:
        dictionary grouped by matches
    '''
    k = 0
    bill_id = 0
    bills = {}
    bad_count = 0
    for urls in ls:
        for url,state in urls:
            try:
                print "bill_id: " + str(bill_id)
                bills[bill_id] = {}
                doc = urllib2.urlopen(url).read()
                text = parser.from_buffer(doc)['content'] 
                bills[bill_id]['url'] = url
                bills[bill_id]['text'] = text
                bills[bill_id]['match'] = k
                bills[bill_id]['state'] = state
            except:
                pass
                bad_count += 1
                print 'bad_count: ', bad_count
            bill_id += 1
        k += 1

    try:
        for bill in bills.keys():
            if bills[bill] == {} or bills[bill]['text'] == '' \
                or bills[bill]['text'] == None:
                
                del bills[bill]
    except:
        pass

    #get more evaluation bills
    eval_bills = grab_more_eval_bills()
    for bills in eval_bills:
        k +=1
        for bill_text in bill:
            bill_id += 1

            bills[bill_id] = {}
            bills[bill_id]['text'] = text
            bills[bill_id]['state'] = state

    return bills

def get_bill_by_id(unique_id):
    es = Elasticsearch(['54.203.12.145:9200', '54.203.12.145:9200'], timeout=300)
    match = es.search(index="state_bills", body={"query": {"match": {'unique_id': unique_id}}})
    bill_text = match['hits']['hits'][0]['_source']['bill_document_first']
    return bill_text

def grab_more_eval_bills():
    with open('../data/evaluation_set/bills_for_evaluation_set.csv') as f:
        bills_list = [row for row in csv.reader(f.read().splitlines())]
        
    bill_ids_list = []
    url_lists = []
    topic_list = []
    for i in range(len(bills_list)):
        state = bills_list[i][1]
        topic = bills_list[i][0]
        bill_number = bills_list[i][2]
        bill_number = re.sub(' ', '', bill_number)
        year = bills_list[i][3]
        url = bills_list[i][6]
        unique_id = str(state + '_' + year + '_' + bill_number)
        topic_list.append(topic)
        bill_ids_list.append(unique_id)
        url_lists.append(url)

    bills_ids = zip(bill_ids_list, url_lists)

    bills_text = []
    state_list = []
    for i in range(len(bills_ids)):
        try:
            bill_text = get_bill_by_id(bills_ids[i][0])
        except IndexError:
            try:
                url = bills_ids[i][1]
                doc = urllib.urlopen(url)
                bill_text = parser.from_buffer(doc)['content']
                print url
            except IOError:
                bill_text = None
        bills_text.append(bill_text)
        state = bills_ids[i][0][0:2]
        state_list.append(state)

    bills_state = zip(bills_text, state_list, topic_list)

    bill_type_1 = []
    bill_type_2 = []
    for bill in bills_state:
        if bill[-1] == 'Adult Guardianship and Protective Proceedings Jurisdiction Act':
            bill_type_1.append((bill[0],bill[1]))
        else:
            bill_type_2.append((bill[0],bill[1]))

    return [bill_type_2, bill_type_1]

def create_save_bills(bill_list):
    bills = create_bills(bill_list)
    with open('../data/bills.p', 'wb') as fp:
        pickle.dump(bills, fp)

    return bills


def load_bills():
    with open('../data/bills.p','rb') as fp:
        bills =pickle.load(fp)

    return bills

def load_pickle(name):
    with open('../data/{0}.p'.format(name),'rb') as fp:
        f =pickle.load(fp)

    return f

def load_scores():
    scores = np.load('../data/scores.npy')

    return scores


def save_results(results):
    with open('../data/results.json','wb') as fp:
        pickle.dump(results, fp)


def load_results():
    with open('../data/results.json','rb') as fp:
        data =pickle.load(fp)
    return data



if __name__ == '__main__':
    #each list in this list of lists contains bills that are matches
    similar_bills = [[('http://www.azleg.gov/legtext/52leg/1r/bills/hb2505p.pdf', 'az'),
    ('http://www.legis.state.ak.us/basis/get_bill_text.asp?hsid=SB0012B&session=29', 'ak' ),
    ('http://www.capitol.hawaii.gov/session2015/bills/HB9_.PDF', 'hi'),
    ('http://www.capitol.hawaii.gov/session2015/bills/HB1047_.PDF', 'hi'),
    ('http://flsenate.gov/Session/Bill/2015/1490/BillText/Filed/HTML','fl'),
    ('http://ilga.gov/legislation/fulltext.asp?DocName=09900SB1836&GA=99&SessionId=88&DocTypeId=SB&LegID=88673&DocNum=1836&GAID=13&Session=&print=true','il'),
    ('http://www.legis.la.gov/Legis/ViewDocument.aspx?d=933306', 'la'),
    ('http://mgaleg.maryland.gov/2015RS/bills/sb/sb0040f.pdf', 'md'),
    ('http://www.legislature.mi.gov/documents/2015-2016/billintroduced/House/htm/2015-HIB-4167.htm', 'mi'),
    ('https://www.revisor.mn.gov/bills/text.php?number=HF549&version=0&session=ls89&session_year=2015&session_number=0','mn'),
    ('http://www.njleg.state.nj.us/2014/Bills/A2500/2354_R2.HTM','nj'),
    ('http://assembly.state.ny.us/leg/?sh=printbill&bn=A735&term=2015','ny'),
    ('http://www.ncga.state.nc.us/Sessions/2015/Bills/House/HTML/H270v1.html','nc'),
    ('https://olis.leg.state.or.us/liz/2015R1/Downloads/MeasureDocument/HB2005/A-Engrossed','or'),
    ('https://olis.leg.state.or.us/liz/2015R1/Downloads/MeasureDocument/SB947/Introduced','or'),
    ('http://www.legis.state.pa.us/CFDOCS/Legis/PN/Public/btCheck.cfm?txtType=HTM&sessYr=2015&sessInd=0&billBody=H&billTyp=B&billNbr=0624&pn=0724', 'pa'),
    ('http://www.scstatehouse.gov/sess121_2015-2016/prever/172_20141203.htm','sc'),
    ('http://lawfilesext.leg.wa.gov/Biennium/2015-16/Htm/Bills/House%20Bills/1356.htm', 'wa'),
    ('http://www.legis.state.wv.us/Bill_Status/bills_text.cfm?billdoc=hb2874%20intr.htm&yr=2015&sesstype=RS&i=2874','wv'),
    ('http://www.legis.state.wv.us/Bill_Status/bills_text.cfm?billdoc=hb2874%20intr.htm&yr=2015&sesstype=RS&i=2874', 'wv'),
    ('ftp://ftp.cga.ct.gov/2015/tob/h/2015HB-06784-R00-HB.htm','ct'),
    ('http://www.capitol.hawaii.gov/session2015/bills/SB129_.PDF','hi'),
    ('http://nebraskalegislature.gov/FloorDocs/104/PDF/Intro/LB493.pdf', 'ne'),
    ('http://www.gencourt.state.nh.us/legislation/2015/HB0600.html', 'nh')],
    [('http://alecexposed.org/w/images/2/2d/7K5-No_Sanctuary_Cities_for_Illegal_Immigrants_Act_Exposed.pdf', None),
    ('http://www.kslegislature.org/li_2012/b2011_12/measures/documents/hb2578_00_0000.pdf', 'ks'),
    ('http://flsenate.gov/Session/Bill/2011/0237/BillText/Filed/HTML','fl'),
    ('http://openstates.org/al/bills/2012rs/SB211/','al'),
    ('http://le.utah.gov/~2011/bills/static/HB0497.html','ut'),
    ('http://webserver1.lsb.state.ok.us/cf_pdf/2013-14%20FLR/HFLR/HB1436%20HFLR.PDF','ok')],
    [('http://www.alec.org/model-legislation/the-disclosure-of-hydraulic-fracturing-fluid-composition-act/', None),
    ('ftp://ftp.legis.state.tx.us/bills/82R/billtext/html/house_bills/HB03300_HB03399/HB03328S.htm', 'tx')],
    [('http://www.legislature.mi.gov/(S(ntrjry55mpj5pv55bv1wd155))/documents/2005-2006/billintroduced/House/htm/2005-HIB-5153.htm', 'mi'),
    ('http://www.schouse.gov/sess116_2005-2006/bills/4301.htm','sc'),
    ('http://www.lrc.ky.gov/record/06rs/SB38.htm', 'ky'),
    ('http://www.okhouse.gov/Legislation/BillFiles/hb2615cs%20db.PDF', 'ok'),
    ('http://state.tn.us/sos/acts/105/pub/pc0210.pdf', 'tn'),
    ('https://docs.legis.wisconsin.gov/2011/related/proposals/ab69', 'wi'),
    ('http://legisweb.state.wy.us/2008/Enroll/HB0137.pdf', 'wy'),
    ('http://www.kansas.gov/government/legislative/bills/2006/366.pdf', 'ks'),
    ('http://billstatus.ls.state.ms.us/documents/2006/pdf/SB/2400-2499/SB2426SG.pdf', 'mi')],
    [('http://www.alec.org/model-legislation/state-withdrawal-from-regional-climate-initiatives/', None),
    ('http://www.legislature.mi.gov/documents/2011-2012/resolutionintroduced/House/htm/2011-HIR-0134.htm', 'mi'),
    ('http://www.nmlegis.gov/Sessions/11%20Regular/memorials/house/HJM024.html', 'nm')],
    [('http://alecexposed.org/w/images/9/90/7J1-Campus_Personal_Protection_Act_Exposed.pdf', None),
    ('ftp://ftp.legis.state.tx.us/bills/831/billtext/html/house_bills/HB00001_HB00099/HB00056I.htm', 'tx')],
    # [
    # ('http://essexuu.org/ctstat.html', 'ct'), we don't have connecituc
    # ('http://alisondb.legislature.state.al.us/alison/codeofalabama/constitution/1901/CA-170364.htm', 'al')],
    [('http://www.legis.state.ak.us/basis/get_bill_text.asp?hsid=HB0162A&session=27', 'ak'),
    ('https://legiscan.com/AL/text/HB19/id/327641/Alabama-2011-HB19-Enrolled.pdf', 'al'),
    ('http://www.leg.state.co.us/clics/clics2012a/csl.nsf/fsbillcont3/0039C9417C9D9D5D87257981007F3CC9?open&file=1111_01.pdf', 'co'),
    ('http://www.capitol.hawaii.gov/session2012/Bills/HB2221_.PDF', 'hi'),
    ('http://ilga.gov/legislation/fulltext.asp?DocName=09700HB3058&GA=97&SessionId=84&DocTypeId=HB&LegID=60409&DocNum=3058&GAID=11&Session=&print=true', 'il'),
    ('http://coolice.legis.iowa.gov/Legislation/84thGA/Bills/SenateFiles/Introduced/SF142.html', 'ia'),
    ('ftp://www.arkleg.state.ar.us/Bills/2011/Public/HB1797.pdf','ar'),
    ('http://billstatus.ls.state.ms.us/documents/2012/html/HB/0900-0999/HB0921SG.htm', 'ms'),
    ('http://www.leg.state.nv.us/Session/76th2011/Bills/SB/SB373.pdf', 'nv'),
    ('http://www.njleg.state.nj.us/2012/Bills/A1000/674_I1.HTM', 'nj'),
    ('http://webserver1.lsb.state.ok.us/cf_pdf/2011-12%20INT/hB/HB2821%20INT.PDF', 'ok'),
    ('http://www.legis.state.pa.us/CFDOCS/Legis/PN/Public/btCheck.cfm?txtType=PDF&sessYr=2011&sessInd=0&billBody=H&billTyp=B&billNbr=0934&pn=1003', 'pa'),
    ('http://www.capitol.tn.gov/Bills/107/Bill/SB0016.pdf', 'tn')],
    [('http://www.legislature.idaho.gov/idstat/Title39/T39CH6SECT39-608.htm', 'id'),
    ('http://www.legis.nd.gov/cencode/t12-1c20.pdf?20150708171557', 'nd')]
    ]

    # bills = create_save_bills(similar_bills)
    bills = load_bills()

    print 'testing local alignment'
    e = DocExperiment(bills, LocalAlignment)

    e.evaluate_algorithm()

    with open('../data/experiment.p', 'wb') as fp:
        pickle.dump(e, fp)

    # print 'testing section local alignment'
    # e = SectionExperiment(bills, SectionLocalAlignment)
    # e.evaluate_algorithm()

    # with open('../data/results_section.p', 'wb') as fp:
    #     pickle.dump(e.results, fp)

