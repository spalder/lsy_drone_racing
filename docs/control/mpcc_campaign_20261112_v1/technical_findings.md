# Detailed technical findings



## Stage A



E02_contour_weight_700: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].

E09_attitude_rate_weight_0p05: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].

E09_attitude_rate_weight_0p075: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].

F1: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].

F1_2: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].

F2: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].

G01_gate_offset_0p144: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].

G07_pole_width_0p4375: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].

RECHECK_R24: 1 episodes with nonzero solver status or explicit fallback; 1 of those episodes finished. Affected seeds/ticks: [(1034792039, 3, 3)].

REF: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].



**E09_attitude_rate_weight_0p05 → E09_attitude_rate_weight_0p075:** -3.00 pp completion, conservative 95% interval [-10.86, 5.32]; exact McNemar Holm p=1. Rescues [102648032]; regressions [290241093, 417159657, 999614311, 1333610997]. Shared-success time difference 0.02219 s on 64 races. These states are genuinely paired; stage role governs whether this is screening or independent evidence.



rescues losing mechanisms: {'pole_contact': 1}.

Seed 102648032 (rescues): starting position [-1.4656989574432373, 0.7735235691070557, 0.01563688926398754]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.36217203736305237, -0.66191565990448, 1.3006322383880615]]].

regressions losing mechanisms: {'gate_contact': 2, 'pole_contact': 2}.

Seed 290241093 (regressions): starting position [-1.5822173357009888, 0.7253187894821167, 0.022282380610704422]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.09161295741796494, -0.7274853587150574, 1.2546881437301636]]].

Seed 417159657 (regressions): starting position [-1.4173221588134766, 0.6940734386444092, 0.017298026010394096]; losing mechanism pole_contact, gate occurrences passed 4, pre-warp impact position [[[1.1626574993133545, 0.4113129675388336, 1.1869487762451172]]].

Seed 999614311 (regressions): starting position [-1.5226951837539673, 0.6745267510414124, 0.02313629537820816]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.2708008289337158, -0.2404109239578247, 0.9086558818817139]]].

Seed 1333610997 (regressions): starting position [-1.404129147529602, 0.7264498472213745, 0.013225317001342773]; losing mechanism gate_contact, gate occurrences passed 0, pre-warp impact position [[[0.3869059383869171, 0.33844873309135437, 0.6909229755401611]]].



**F1 → F1_2:** -2.00 pp completion, conservative 95% interval [-7.88, 4.12]; exact McNemar Holm p=1. Rescues []; regressions [1306588657, 1446109330]. Shared-success time difference -0.00456 s on 79 races. These states are genuinely paired; stage role governs whether this is screening or independent evidence.



rescues losing mechanisms: {}.

regressions losing mechanisms: {'gate_contact': 1, 'pole_contact': 1}.

Seed 1306588657 (regressions): starting position [-1.5858319997787476, 0.689737856388092, 0.012817763723433018]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1443992853164673, -0.4243355393409729, 1.198015570640564]]].

Seed 1446109330 (regressions): starting position [-1.5245321989059448, 0.6946348547935486, 0.028592821210622787]; losing mechanism pole_contact, gate occurrences passed 1, pre-warp impact position [[[0.7634087204933167, 0.05001174286007881, 0.804410994052887]]].



**F1 → G07_pole_width_0p4375:** 6.00 pp completion, conservative 95% interval [-6.49, 17.89]; exact McNemar Holm p=1. Rescues [348702060, 769556247, 1128742187, 1212342216, 1262189215, 1327080486, 1406291547, 1425504227, 1954395695, 2087983571]; regressions [151562433, 476286568, 1062172283, 1306588657]. Shared-success time difference 0.02727 s on 77 races. These states are genuinely paired; stage role governs whether this is screening or independent evidence.



rescues losing mechanisms: {'pole_contact': 9, 'gate_contact': 1}.

Seed 348702060 (rescues): starting position [-1.5065016746520996, 0.7295050024986267, 0.024470984935760498]; losing mechanism pole_contact, gate occurrences passed 1, pre-warp impact position [[[0.813317060470581, 0.08234231919050217, 0.6714879274368286]]].

Seed 769556247 (rescues): starting position [-1.5367978811264038, 0.8064297437667847, 0.019620858132839203]; losing mechanism gate_contact, gate occurrences passed 0, pre-warp impact position [[[0.5024393200874329, 0.32344093918800354, 0.6625959277153015]]].

Seed 1128742187 (rescues): starting position [-1.4165723323822021, 0.7878904342651367, 0.011262519285082817]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.39763906598091125, -0.621860921382904, 1.3040907382965088]]].

Seed 1212342216 (rescues): starting position [-1.4899588823318481, 0.8286321759223938, 0.018157143145799637]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.41465967893600464, -0.7897539138793945, 1.2648719549179077]]].

Seed 1262189215 (rescues): starting position [-1.4847716093063354, 0.7972506880760193, 0.02486282028257847]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.39955973625183105, -0.7861369252204895, 1.2794134616851807]]].

Seed 1327080486 (rescues): starting position [-1.5156294107437134, 0.7804650068283081, 0.018307456746697426]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.426260381937027, -0.7981133460998535, 1.296154499053955]]].

Seed 1406291547 (rescues): starting position [-1.457675576210022, 0.8331835269927979, 0.018767856061458588]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.45572787523269653, -0.7538342475891113, 1.3367177248001099]]].

Seed 1425504227 (rescues): starting position [-1.4862200021743774, 0.7299135327339172, 0.02211526408791542]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.3627593517303467, -0.24438272416591644, 0.8014703989028931]]].

Seed 1954395695 (rescues): starting position [-1.5940760374069214, 0.712060809135437, 0.01659167744219303]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.502206027507782, -0.6867773532867432, 1.2300293445587158]]].

Seed 2087983571 (rescues): starting position [-1.4752753973007202, 0.8451372981071472, 0.011205627582967281]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.3963184356689453, -0.7952268719673157, 1.3343217372894287]]].

regressions losing mechanisms: {'gate_contact': 4}.

Seed 151562433 (regressions): starting position [-1.460597276687622, 0.8264182209968567, 0.015618063509464264]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1899293661117554, -0.276332288980484, 1.0368752479553223]]].

Seed 476286568 (regressions): starting position [-1.4177069664001465, 0.729201078414917, 0.024486947804689407]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.078906774520874, -0.21553181111812592, 1.1695798635482788]]].

Seed 1062172283 (regressions): starting position [-1.401488184928894, 0.751164972782135, 0.012986013665795326]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.15658394992351532, -0.711467444896698, 1.2037960290908813]]].

Seed 1306588657 (regressions): starting position [-1.5858319997787476, 0.689737856388092, 0.012817763723433018]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1558420658111572, -0.43017080426216125, 1.1863528490066528]]].



Common difficulty: 8/100 seeds defeated every tested candidate; 58/100 were finished by every candidate. All-failed seeds: [363954350, 597316325, 670521555, 999246608, 1308118783, 1398587418, 1684219294, 1972471467]. This assesses robustness within the candidate set, not the prevalence of universally impossible races.



## Stage B



E09_attitude_rate_weight_0p05: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].

F1: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].

F1_2: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].

G07_pole_width_0p4375: 1 episodes with nonzero solver status or explicit fallback; 1 of those episodes finished. Affected seeds/ticks: [(1246617712, 1, 1)].

RECHECK_R24: 0 episodes with nonzero solver status or explicit fallback; 0 of those episodes finished. Affected seeds/ticks: [].



**F1 → F1_2:** -0.50 pp completion, conservative 95% interval [-5.30, 4.35]; exact McNemar Holm p=1. Rescues [65408800, 1024363835, 1438976770]; regressions [98977452, 510254869, 1410140122, 1972607575]. Shared-success time difference -0.00333 s on 168 races. These states are genuinely paired; stage role governs whether this is screening or independent evidence.



rescues losing mechanisms: {'pole_contact': 3}.

Seed 65408800 (rescues): starting position [-1.5653899908065796, 0.6896209716796875, 0.024006428197026253]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4323410391807556, -0.7928093075752258, 1.2588133811950684]]].

Seed 1024363835 (rescues): starting position [-1.5792094469070435, 0.8256208300590515, 0.011523439548909664]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4306957721710205, -0.7777843475341797, 1.2919892072677612]]].

Seed 1438976770 (rescues): starting position [-1.5834077596664429, 0.8333084583282471, 0.027300136163830757]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.2817972004413605, -0.7075014710426331, 1.2440381050109863]]].

regressions losing mechanisms: {'gate_contact': 3, 'pole_contact': 1}.

Seed 98977452 (regressions): starting position [-1.5374786853790283, 0.7472051382064819, 0.02498188428580761]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.1602550446987152, -0.8169851303100586, 1.237321376800537]]].

Seed 510254869 (regressions): starting position [-1.5973899364471436, 0.7044265866279602, 0.021303290501236916]; losing mechanism pole_contact, gate occurrences passed 4, pre-warp impact position [[[1.2210756540298462, 0.46176978945732117, 1.1203210353851318]]].

Seed 1410140122 (regressions): starting position [-1.4417115449905396, 0.6896482110023499, 0.02776806801557541]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.04482726752758026, -0.7751579284667969, 1.1852068901062012]]].

Seed 1972607575 (regressions): starting position [-1.5943228006362915, 0.7790186405181885, 0.028333187103271484]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1377390623092651, -0.3202231824398041, 1.2242441177368164]]].



**F1 → G07_pole_width_0p4375:** 0.00 pp completion, conservative 95% interval [-7.13, 7.13]; exact McNemar Holm p=1. Rescues [65408800, 95891859, 323367541, 360983529, 1024363835, 1117178632, 1438976770, 1564490720, 1578518184]; regressions [167701423, 457839674, 861344879, 1135897820, 1303804400, 1499172520, 1941167208, 1972607575, 2050586991]. Shared-success time difference 0.03288 s on 163 races. These states are genuinely paired; stage role governs whether this is screening or independent evidence.



rescues losing mechanisms: {'pole_contact': 7, 'gate_contact': 2}.

Seed 65408800 (rescues): starting position [-1.5653899908065796, 0.6896209716796875, 0.024006428197026253]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4323410391807556, -0.7928093075752258, 1.2588133811950684]]].

Seed 95891859 (rescues): starting position [-1.457477331161499, 0.8283860683441162, 0.0299301166087389]; losing mechanism gate_contact, gate occurrences passed 0, pre-warp impact position [[[0.5188856720924377, 0.3416258990764618, 0.6347252130508423]]].

Seed 323367541 (rescues): starting position [-1.528947114944458, 0.8020044565200806, 0.015383226796984673]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.3086808919906616, -0.34976890683174133, 0.7465635538101196]]].

Seed 360983529 (rescues): starting position [-1.5763112306594849, 0.7400009036064148, 0.01984712854027748]; losing mechanism pole_contact, gate occurrences passed 1, pre-warp impact position [[[0.8341932892799377, 0.19427785277366638, 0.6624558568000793]]].

Seed 1024363835 (rescues): starting position [-1.5792094469070435, 0.8256208300590515, 0.011523439548909664]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4306957721710205, -0.7777843475341797, 1.2919892072677612]]].

Seed 1117178632 (rescues): starting position [-1.528833270072937, 0.8043739795684814, 0.01883043348789215]; losing mechanism gate_contact, gate occurrences passed 0, pre-warp impact position [[[0.5565565228462219, 0.30689090490341187, 0.6198933124542236]]].

Seed 1438976770 (rescues): starting position [-1.5834077596664429, 0.8333084583282471, 0.027300136163830757]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.2817972004413605, -0.7075014710426331, 1.2440381050109863]]].

Seed 1564490720 (rescues): starting position [-1.5752620697021484, 0.6687853932380676, 0.018320569768548012]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.43964555859565735, -0.6008569002151489, 1.1998536586761475]]].

Seed 1578518184 (rescues): starting position [-1.5068798065185547, 0.7313873767852783, 0.010003523901104927]; losing mechanism pole_contact, gate occurrences passed 1, pre-warp impact position [[[0.8013997673988342, 0.06521515548229218, 0.7069091200828552]]].

regressions losing mechanisms: {'gate_contact': 9}.

Seed 167701423 (regressions): starting position [-1.4270521402359009, 0.7812114953994751, 0.02905123494565487]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[0.10251650214195251, -0.7119781374931335, 1.2120007276535034]]].

Seed 457839674 (regressions): starting position [-1.4937134981155396, 0.8179327249526978, 0.021132368594408035]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.0799813270568848, -0.31890690326690674, 1.113868236541748]]].

Seed 861344879 (regressions): starting position [-1.5180292129516602, 0.8494808077812195, 0.028843848034739494]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1754523515701294, -0.06644324958324432, 1.0843069553375244]]].

Seed 1135897820 (regressions): starting position [-1.5617544651031494, 0.6773281693458557, 0.01422992441803217]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1194442510604858, -0.49635905027389526, 1.1516467332839966]]].

Seed 1303804400 (regressions): starting position [-1.5263216495513916, 0.6764718890190125, 0.010731999762356281]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.198543906211853, -0.17940011620521545, 1.055037260055542]]].

Seed 1499172520 (regressions): starting position [-1.4484113454818726, 0.7947854399681091, 0.01860281452536583]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.15953844785690308, -0.75040203332901, 1.2381025552749634]]].

Seed 1941167208 (regressions): starting position [-1.4500590562820435, 0.7621883749961853, 0.025413326919078827]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.2132850885391235, -0.4046633243560791, 1.1461379528045654]]].

Seed 1972607575 (regressions): starting position [-1.5943228006362915, 0.7790186405181885, 0.028333187103271484]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.175085186958313, -0.2891739308834076, 1.1807218790054321]]].

Seed 2050586991 (regressions): starting position [-1.5553888082504272, 0.6996892690658569, 0.013962415978312492]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[0.032923247665166855, -0.7750408053398132, 1.12031090259552]]].



Common difficulty: 18/200 seeds defeated every tested candidate; 125/200 were finished by every candidate. All-failed seeds: [154058469, 209658773, 233904126, 563770046, 670226498, 694015247, 825794356, 834717831, 842534193, 1041441501, 1074867695, 1142148692, 1282505073, 1499149835, 1522367608, 1540154773, 1631762131, 1759858621]. This assesses robustness within the candidate set, not the prevalence of universally impossible races.



## Stage C



F1: 2 episodes with nonzero solver status or explicit fallback; 2 of those episodes finished. Affected seeds/ticks: [(835365463, 6, 6), (1755968130, 1, 1)].

F1_2: 1 episodes with nonzero solver status or explicit fallback; 1 of those episodes finished. Affected seeds/ticks: [(835365463, 6, 6)].

G07_pole_width_0p4375: 6 episodes with nonzero solver status or explicit fallback; 5 of those episodes finished. Affected seeds/ticks: [(198423194, 11, 11), (675975053, 3, 3), (835365463, 7, 7), (877126514, 7, 7), (1617635227, 7, 7), (1755968130, 2, 2)].



**F1 → F1_2:** 1.60 pp completion, conservative 95% interval [-1.41, 4.57]; exact McNemar Holm p=0.23064. Rescues [340220063, 561839061, 730545249, 884535409, 995724273, 1186325116, 1193569596, 1230436720, 1480753386, 1643139230, 1680319165, 1849611674, 2063863452, 2113394988]; regressions [97600999, 143281452, 564183951, 772579058, 1285735503, 2146829813]. Shared-success time difference -0.00489 s on 393 races. These states are genuinely paired; stage role governs whether this is screening or independent evidence.



rescues losing mechanisms: {'pole_contact': 7, 'gate_contact': 7}.

Seed 340220063 (rescues): starting position [-1.5981738567352295, 0.7471352815628052, 0.020445551723241806]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.333146095275879, -0.41409242153167725, 0.8302096128463745]]].

Seed 561839061 (rescues): starting position [-1.4084960222244263, 0.8099210262298584, 0.01920611411333084]; losing mechanism gate_contact, gate occurrences passed 0, pre-warp impact position [[[0.5464613437652588, 0.27649009227752686, 0.6058489680290222]]].

Seed 730545249 (rescues): starting position [-1.488480567932129, 0.8064724206924438, 0.012698967009782791]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.3958567380905151, -0.16515427827835083, 0.7095350623130798]]].

Seed 884535409 (rescues): starting position [-1.567173719406128, 0.6653313040733337, 0.017854679375886917]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1952149868011475, -0.3050253093242645, 1.1293911933898926]]].

Seed 995724273 (rescues): starting position [-1.4484275579452515, 0.7023401856422424, 0.017679493874311447]; losing mechanism pole_contact, gate occurrences passed 4, pre-warp impact position [[[1.1426305770874023, 0.45062780380249023, 1.2707889080047607]]].

Seed 1186325116 (rescues): starting position [-1.5183568000793457, 0.7586309909820557, 0.026573657989501953]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.2012598514556885, -0.4184999465942383, 1.2197291851043701]]].

Seed 1193569596 (rescues): starting position [-1.5406497716903687, 0.7601979970932007, 0.028013009577989578]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.15734882652759552, -0.7163137793540955, 1.1571004390716553]]].

Seed 1230436720 (rescues): starting position [-1.5975719690322876, 0.7451211810112, 0.017150020226836205]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.423369824886322, -0.782825231552124, 1.269108772277832]]].

Seed 1480753386 (rescues): starting position [-1.468554139137268, 0.7677767276763916, 0.010442144237458706]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.152409315109253, -0.2734476327896118, 1.137520432472229]]].

Seed 1643139230 (rescues): starting position [-1.5200605392456055, 0.8372514843940735, 0.011654922738671303]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4723230004310608, -0.740567147731781, 1.4290101528167725]]].

Seed 1680319165 (rescues): starting position [-1.4699045419692993, 0.6831494569778442, 0.020824119448661804]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.29077982902526855, -0.6608604192733765, 1.2213186025619507]]].

Seed 1849611674 (rescues): starting position [-1.5759295225143433, 0.735730767250061, 0.028444133698940277]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.2032187581062317, -0.6677539348602295, 1.2914873361587524]]].

Seed 2063863452 (rescues): starting position [-1.5242854356765747, 0.6806603670120239, 0.013624200597405434]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.3303545713424683, -0.14022329449653625, 0.7746021151542664]]].

Seed 2113394988 (rescues): starting position [-1.437506079673767, 0.7465741038322449, 0.021781671792268753]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.20235678553581238, -0.7260810732841492, 1.25059175491333]]].

regressions losing mechanisms: {'gate_contact': 6}.

Seed 97600999 (regressions): starting position [-1.4750789403915405, 0.8270905017852783, 0.01091813761740923]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.16143949329853058, -0.7711385488510132, 1.2322001457214355]]].

Seed 143281452 (regressions): starting position [-1.4178743362426758, 0.7774215936660767, 0.028822865337133408]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.0848987102508545, -0.18068227171897888, 1.2373102903366089]]].

Seed 564183951 (regressions): starting position [-1.5677777528762817, 0.8240646123886108, 0.022286836057901382]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.185827612876892, -0.0271439366042614, 1.203133225440979]]].

Seed 772579058 (regressions): starting position [-1.5478578805923462, 0.7161840200424194, 0.024721067398786545]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.24377961456775665, -0.710267961025238, 1.2416797876358032]]].

Seed 1285735503 (regressions): starting position [-1.434475064277649, 0.7579748630523682, 0.016648974269628525]; losing mechanism gate_contact, gate occurrences passed 2, pre-warp impact position [[[0.5524505972862244, 0.6775655150413513, 1.0249505043029785]]].

Seed 2146829813 (regressions): starting position [-1.5337480306625366, 0.71480393409729, 0.016395876184105873]; losing mechanism gate_contact, gate occurrences passed 0, pre-warp impact position [[[0.47193264961242676, 0.2752783000469208, 0.7760511636734009]]].



**F1 → G07_pole_width_0p4375:** 3.60 pp completion, conservative 95% interval [-1.27, 8.40]; exact McNemar Holm p=0.074238. Rescues [144553943, 197263640, 298460662, 340220063, 417995290, 436919894, 439263216, 730545249, 751189091, 884535409, 918652596, 947229978, 961821027, 995724273, 1063952968, 1185804483, 1186325116, 1230436720, 1271528109, 1305371719, 1309878891, 1369962895, 1465055580, 1508866518, 1528316954, 1580089131, 1641457685, 1643139230, 1680319165, 1682518045, 1757148817, 1867742022, 1936921348, 1956172557, 2010746506, 2027562568, 2052215102, 2113394988]; regressions [97600999, 143281452, 224895969, 235222051, 363191354, 675975053, 699121524, 772579058, 809989217, 871726246, 1294093695, 1309062909, 1325475153, 1391320898, 1616249224, 1804799460, 2020561974, 2030397303, 2142729424, 2146829813]. Shared-success time difference 0.03409 s on 379 races. These states are genuinely paired; stage role governs whether this is screening or independent evidence.



rescues losing mechanisms: {'pole_contact': 27, 'gate_contact': 11}.

Seed 144553943 (rescues): starting position [-1.5771512985229492, 0.7647988796234131, 0.026687178760766983]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.45211711525917053, -0.8002198934555054, 1.3353317975997925]]].

Seed 197263640 (rescues): starting position [-1.5240896940231323, 0.6972306966781616, 0.0205145962536335]; losing mechanism pole_contact, gate occurrences passed 1, pre-warp impact position [[[0.868870735168457, 0.051742032170295715, 0.7177399396896362]]].

Seed 298460662 (rescues): starting position [-1.4066236019134521, 0.6640216112136841, 0.026405448094010353]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.09361322969198227, -0.7433077692985535, 1.2418134212493896]]].

Seed 340220063 (rescues): starting position [-1.5981738567352295, 0.7471352815628052, 0.020445551723241806]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.333146095275879, -0.41409242153167725, 0.8302096128463745]]].

Seed 417995290 (rescues): starting position [-1.4377367496490479, 0.8327592015266418, 0.011677948758006096]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.45316508412361145, -0.7756506204605103, 1.3222519159317017]]].

Seed 436919894 (rescues): starting position [-1.5048339366912842, 0.8393557667732239, 0.023701105266809464]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.42982545495033264, -0.8102684020996094, 1.3051981925964355]]].

Seed 439263216 (rescues): starting position [-1.5551211833953857, 0.7938095927238464, 0.012923466973006725]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.170641541481018, -0.1904754340648651, 1.1958801746368408]]].

Seed 730545249 (rescues): starting position [-1.488480567932129, 0.8064724206924438, 0.012698967009782791]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.3958567380905151, -0.16515427827835083, 0.7095350623130798]]].

Seed 751189091 (rescues): starting position [-1.4562773704528809, 0.8103505969047546, 0.013403374701738358]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.117120623588562, -0.25257423520088196, 1.217025637626648]]].

Seed 884535409 (rescues): starting position [-1.567173719406128, 0.6653313040733337, 0.017854679375886917]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1952149868011475, -0.3050253093242645, 1.1293911933898926]]].

Seed 918652596 (rescues): starting position [-1.5394552946090698, 0.6593851447105408, 0.027711020782589912]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.3566324710845947, -0.19764064252376556, 0.7486010193824768]]].

Seed 947229978 (rescues): starting position [-1.5290852785110474, 0.7358522415161133, 0.011674003675580025]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.3169605731964111, -0.39648640155792236, 0.7055079936981201]]].

Seed 961821027 (rescues): starting position [-1.5063050985336304, 0.8374536037445068, 0.02338547632098198]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.43249785900115967, -0.7797264456748962, 1.252497911453247]]].

Seed 995724273 (rescues): starting position [-1.4484275579452515, 0.7023401856422424, 0.017679493874311447]; losing mechanism pole_contact, gate occurrences passed 4, pre-warp impact position [[[1.1426305770874023, 0.45062780380249023, 1.2707889080047607]]].

Seed 1063952968 (rescues): starting position [-1.493708848953247, 0.7727275490760803, 0.01795058883726597]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.199971318244934, -0.20663797855377197, 1.192671537399292]]].

Seed 1185804483 (rescues): starting position [-1.529072880744934, 0.6581436991691589, 0.023695893585681915]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.3701390027999878, -0.43286648392677307, 0.6903546452522278]]].

Seed 1186325116 (rescues): starting position [-1.5183568000793457, 0.7586309909820557, 0.026573657989501953]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.2012598514556885, -0.4184999465942383, 1.2197291851043701]]].

Seed 1230436720 (rescues): starting position [-1.5975719690322876, 0.7451211810112, 0.017150020226836205]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.423369824886322, -0.782825231552124, 1.269108772277832]]].

Seed 1271528109 (rescues): starting position [-1.4562982320785522, 0.6869438290596008, 0.0143567631021142]; losing mechanism pole_contact, gate occurrences passed 1, pre-warp impact position [[[0.798791229724884, 0.1111249253153801, 0.8277856707572937]]].

Seed 1305371719 (rescues): starting position [-1.5257174968719482, 0.7586123943328857, 0.019676534458994865]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4396720826625824, -0.7739787697792053, 1.3561509847640991]]].

Seed 1309878891 (rescues): starting position [-1.4048467874526978, 0.8126469850540161, 0.012154871597886086]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4238036274909973, -0.7682675123214722, 1.3010296821594238]]].

Seed 1369962895 (rescues): starting position [-1.410021185874939, 0.81697016954422, 0.023371029645204544]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4159806966781616, -0.7722138166427612, 1.2959303855895996]]].

Seed 1465055580 (rescues): starting position [-1.4592301845550537, 0.7421941757202148, 0.01505756564438343]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.40917307138442993, -0.8060133457183838, 1.294395089149475]]].

Seed 1508866518 (rescues): starting position [-1.5120731592178345, 0.7928774356842041, 0.024758901447057724]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4108264446258545, -0.7701992392539978, 1.2650680541992188]]].

Seed 1528316954 (rescues): starting position [-1.5805974006652832, 0.731516420841217, 0.01767794042825699]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4309956431388855, -0.7881141901016235, 1.307781457901001]]].

Seed 1580089131 (rescues): starting position [-1.4986079931259155, 0.6852607727050781, 0.027088558301329613]; losing mechanism pole_contact, gate occurrences passed 1, pre-warp impact position [[[0.8145412802696228, 0.05090469494462013, 0.7935596108436584]]].

Seed 1641457685 (rescues): starting position [-1.403509497642517, 0.7427144050598145, 0.017881102859973907]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-1.3675107955932617, -0.44355228543281555, 0.6803262233734131]]].

Seed 1643139230 (rescues): starting position [-1.5200605392456055, 0.8372514843940735, 0.011654922738671303]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4723230004310608, -0.740567147731781, 1.4290101528167725]]].

Seed 1680319165 (rescues): starting position [-1.4699045419692993, 0.6831494569778442, 0.020824119448661804]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.29077982902526855, -0.6608604192733765, 1.2213186025619507]]].

Seed 1682518045 (rescues): starting position [-1.449747920036316, 0.7742464542388916, 0.02323124371469021]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.22217001020908356, -0.6917147040367126, 1.231953740119934]]].

Seed 1757148817 (rescues): starting position [-1.5562033653259277, 0.71852046251297, 0.014977185055613518]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.1899178922176361, -0.7510552406311035, 1.24553382396698]]].

Seed 1867742022 (rescues): starting position [-1.528857946395874, 0.8466984629631042, 0.022642329335212708]; losing mechanism pole_contact, gate occurrences passed 1, pre-warp impact position [[[0.7688960433006287, 0.10968390852212906, 0.620820939540863]]].

Seed 1936921348 (rescues): starting position [-1.5437500476837158, 0.7895610332489014, 0.012765144929289818]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.3997582793235779, -0.7877593636512756, 1.2738031148910522]]].

Seed 1956172557 (rescues): starting position [-1.499725103378296, 0.7665676474571228, 0.0241219624876976]; losing mechanism pole_contact, gate occurrences passed 3, pre-warp impact position [[[-0.4376278221607208, -0.7973792552947998, 1.2705538272857666]]].

Seed 2010746506 (rescues): starting position [-1.4343968629837036, 0.8166790008544922, 0.011204938404262066]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.08055853843688965, -0.7610883116722107, 1.1481854915618896]]].

Seed 2027562568 (rescues): starting position [-1.4934425354003906, 0.829872190952301, 0.01738741807639599]; losing mechanism pole_contact, gate occurrences passed 1, pre-warp impact position [[[0.7853697538375854, 0.056968241930007935, 0.7069015502929688]]].

Seed 2052215102 (rescues): starting position [-1.4648394584655762, 0.6683549880981445, 0.02188601903617382]; losing mechanism gate_contact, gate occurrences passed 0, pre-warp impact position [[[0.5156727433204651, 0.33024612069129944, 0.7478594779968262]]].

Seed 2113394988 (rescues): starting position [-1.437506079673767, 0.7465741038322449, 0.021781671792268753]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.20235678553581238, -0.7260810732841492, 1.25059175491333]]].

regressions losing mechanisms: {'gate_contact': 20}.

Seed 97600999 (regressions): starting position [-1.4750789403915405, 0.8270905017852783, 0.01091813761740923]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.17290098965168, -0.7604365348815918, 1.2512332201004028]]].

Seed 143281452 (regressions): starting position [-1.4178743362426758, 0.7774215936660767, 0.028822865337133408]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1187082529067993, -0.12137090414762497, 1.1763865947723389]]].

Seed 224895969 (regressions): starting position [-1.5758024454116821, 0.8492119908332825, 0.02875661477446556]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.0708911418914795, -0.3287149667739868, 1.188938021659851]]].

Seed 235222051 (regressions): starting position [-1.4963278770446777, 0.7462847828865051, 0.019939875230193138]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1671628952026367, -0.5824019312858582, 1.1904269456863403]]].

Seed 363191354 (regressions): starting position [-1.49587082862854, 0.7551578283309937, 0.027352873235940933]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1344791650772095, -0.17239774763584137, 1.2220131158828735]]].

Seed 675975053 (regressions): starting position [-1.4767074584960938, 0.7870617508888245, 0.029576042667031288]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[0.13396808505058289, -0.7307236790657043, 1.0818960666656494]]].

Seed 699121524 (regressions): starting position [-1.5500404834747314, 0.7873185276985168, 0.022968625649809837]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.17175745964050293, -0.6857079863548279, 1.198939561843872]]].

Seed 772579058 (regressions): starting position [-1.5478578805923462, 0.7161840200424194, 0.024721067398786545]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.23352226614952087, -0.7053699493408203, 1.2571271657943726]]].

Seed 809989217 (regressions): starting position [-1.4736127853393555, 0.6977831125259399, 0.024907663464546204]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.14549759030342102, -0.7875308990478516, 1.223574161529541]]].

Seed 871726246 (regressions): starting position [-1.4623419046401978, 0.8324010372161865, 0.012706024572253227]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.1876809149980545, -0.6850303411483765, 1.240024209022522]]].

Seed 1294093695 (regressions): starting position [-1.492293357849121, 0.8030765056610107, 0.015059525147080421]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1597034931182861, -0.18288399279117584, 1.1853857040405273]]].

Seed 1309062909 (regressions): starting position [-1.430769443511963, 0.731131374835968, 0.011984843760728836]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.9889989495277405, -0.30101722478866577, 1.2043567895889282]]].

Seed 1325475153 (regressions): starting position [-1.4005829095840454, 0.6791016459465027, 0.0282463226467371]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1273918151855469, -0.491569459438324, 1.142530918121338]]].

Seed 1391320898 (regressions): starting position [-1.4832303524017334, 0.7130463123321533, 0.013324904255568981]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.1519079208374023, -0.13767609000205994, 1.1087347269058228]]].

Seed 1616249224 (regressions): starting position [-1.556046962738037, 0.7751532196998596, 0.016964025795459747]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.16922247409820557, -0.7126260995864868, 1.197365164756775]]].

Seed 1804799460 (regressions): starting position [-1.5096509456634521, 0.7912521958351135, 0.025686539709568024]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-0.0773758664727211, -0.7994570136070251, 1.1857287883758545]]].

Seed 2020561974 (regressions): starting position [-1.4036800861358643, 0.7549432516098022, 0.013998135924339294]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.0729808807373047, -0.1773647665977478, 1.0944905281066895]]].

Seed 2030397303 (regressions): starting position [-1.589940071105957, 0.8086330890655518, 0.014645611867308617]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.2493335008621216, -0.0657171756029129, 1.1371368169784546]]].

Seed 2142729424 (regressions): starting position [-1.4415385723114014, 0.7575287818908691, 0.01754859834909439]; losing mechanism gate_contact, gate occurrences passed 3, pre-warp impact position [[[-1.091464638710022, -0.2556799650192261, 1.205199122428894]]].

Seed 2146829813 (regressions): starting position [-1.5337480306625366, 0.71480393409729, 0.016395876184105873]; losing mechanism gate_contact, gate occurrences passed 0, pre-warp impact position [[[0.47355955839157104, 0.2765917479991913, 0.7747005820274353]]].



Common difficulty: 58/500 seeds defeated every tested candidate; 377/500 were finished by every candidate. All-failed seeds: [187181370, 196046762, 225638833, 260739397, 299117191, 331423816, 408391332, 459726537, 476385477, 524623160, 576724474, 646945297, 671617873, 688111135, 707217761, 757876115, 758822043, 826435691, 872042783, 917515469, 919196819, 991980068, 995980658, 1008018249, 1020341689, 1090828852, 1115779938, 1218991991, 1265361585, 1273588581, 1294225236, 1357265113, 1405160088, 1464000442, 1515842442, 1583108781, 1587874397, 1589110856, 1607101950, 1633409644, 1646881649, 1651905454, 1710403566, 1743554978, 1799485298, 1827780119, 1863796793, 1901191232, 1923867522, 1925190089, 1943374775, 1997893667, 2000506906, 2005888375, 2032377630, 2065121057, 2066713904, 2135683996]. This assesses robustness within the candidate set, not the prevalence of universally impossible races.

