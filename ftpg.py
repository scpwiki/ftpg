# -*- coding: utf-8 -*-
# Make sure you rename config.py.example to config.py and fill it out before trying to run this!
# Also, if you're running this on scp-wiki, please have authorization from the Technical Team Captain.
import config
# Used to be a nice API user. Max 240 req/min.
from time import sleep
# Used to convert 2-digit months to names.
from calendar import month_name
# Used to talk to the wikidot API.
from xmlrpclib import ServerProxy
# Used for pulling info from the attribution metadata page.
from bs4 import BeautifulSoup
# Used for sorting the tales-by-date dict.
from collections import OrderedDict
# Used for doing a regex search to find component:preview tags.
from re import search

# Make the connection
s = ServerProxy('https://' + config.wikidot_username + ':' + config.wikidot_api_key + "@www.wikidot.com/xml-rpc-api.php")

# Get the attribution-metadata page to reference later.
attributions = s.pages.get_one({'site': config.wikidot_site, 'page': 'attribution-metadata'})
# Wikidot has a 240 req/min limit on their API.
sleep(0.25)

# Feed the attribution metadata to BeautifulSoup.
a = BeautifulSoup(attributions['html'], 'html.parser')

# Get the list of tales.
taleslist = s.pages.select({'site': config.wikidot_site, "tags_all": ['tale']})

# There are three sets of pages the generator needs to make.
# 1. Tales by Title
# 2. Tales by Author
# 3. Tales by Date
# The workflow goes something like:
# Get the list of tales, get the metadata for each tale which is returned as a dict
# and make a list of dicts, get a blurb from each and store with the dict, then sort
# and format the output. There is a page size limit of 200,000 characters that must be
# tracked as well. We also need to prettify the output and remove HTML or wiki markup.

charactercount = 0

# We use this function to get our finished files from the API queries we perform.


def process_output(list, pagename):
    # This will be our final output. It's a list so we can append in the pythonic way and join at the end, so as not to end
    # up with tons of unneeded string objects.
    output = []
    # We'll create new pages as we hit the 200k character limit.
    pagecount = 1
    # Convert the lists to strings and check their lengths.
    for item in list:
        outstring = ''.join(list[item])
        len_output = len(''.join(output))
        len_outstring = len(outstring)
        if len_output + len_outstring < 200000:
            # We are under the limit, add it to the list and iterate again.
            output.append(outstring)
        else:
            # This string would put the page over the 200k limit.
            # Save a text file or post to wikidot depending on config.wikidot_api_mode,
            # then empty the list and add this.
            if config.wikidot_api_mode is "ro":
                file_object = open(pagename + "-" + str(pagecount), "w")
                file_object.write(''.join(output))
            elif config.wikidot_api_mode is "rw":
                save = s.pages.save_one(
                    {'site': config.wikidot_site, 'page': 'component:' + pagename + '-' + str(pagecount),
                     'content': ''.join(output)})
            output = []
            output.append(outstring)
            # Increment the page counter.
            pagecount += 1

    # Final run for output.
    if config.wikidot_api_mode is "ro":
        file_object = open(pagename + "-" + str(pagecount), "w")
        file_object.write(''.join(output))
    elif config.wikidot_api_mode is "rw":
        # We have to blank the page before submitting a new one or a timeout is likely.
        saveblank = s.pages.save_one({'site': config.wikidot_site, 'page': pagename + '-' + str(pagecount),
                                      'revision_comment': 'Page prepped with ftpg 1.2. (github.com/scpwiki/ftpg)',
                                      'content': ''})
        sleep(0.25)
        # Now we can save the page.
        save = s.pages.save_one({'site': config.wikidot_site, 'page': pagename + '-' + str(pagecount),
                                 'revision_comment': 'Page created with ftpg 1.2. (github.com/scpwiki/ftpg)',
                                 'content': ''.join(output)})
        sleep(0.25)


# Getting metadata can only be done with sets of 10 pages at a time. Given that we have almost 3000 tales to process,
# let's do everything we can to make it go quickly. This function splits a big list into small lists.
def chunks(l, n):
    # We're taking the length of the first argument (the big list), and using the desired length for the second arg.
    for i in range(0, len(l), n):
        # And returning an index range of the appropriate number of items.
        yield l[i:i+n]

tales_chunked = chunks(taleslist, 10)

# Create our list that will hold the dicts.
tales = []

# Create dicts that will hold our formatted output lists. We'll only move them to output when we're ready and there's
# room under the 200k character limit.
t_alpha = {}
t_author = {}
t_date = {}

for taleset in tales_chunked:
    # Get a chunk of metadata.
    metachunk = s.pages.get_meta({'site': config.wikidot_site, 'pages': taleset})
    # Add the chunk to the list.
    tales.append(metachunk)
    # Sleep and repeat if more chunks exist.
    sleep(0.25)

# Now we've got a tales dict that's in chunks of 10 nested dicts, we need to pull them all up to the same level.
t = []
for chunk in tales:
    for tale in chunk:
        t.append(chunk[tale])

# Sort with lambda because using itemgetter results in case-sensitive sorting.
t = sorted(t, key=lambda x: x['title'].lower())

for tale in t:
    # Get the actual content of the article.
    article = s.pages.get_one({'site': config.wikidot_site, 'page': tale['fullname']})
    # Feed the HTML to BeautifulSoup.
    soup = BeautifulSoup(article['html'], 'html.parser')
    # Make use of BS4's get_text() to strip out HTML. Remove line breaks.
    tale['excerpt'] = soup.get_text().replace('\n', ' ')
    # Split the text before 200 characters at the closest word, and add an ellipsis.
    tale['excerpt'] = ' '.join(tale['excerpt'][:200 + 1].split(' ')[0:-1]) + '...'
    # If there is a component:preview module used, use it instead.
    preview = search('\[\[include component:preview text=(.*)]]', article['content'])
    if preview is not None:
        tale['excerpt'] = preview.group(1)
        print(tale['fullname'])
    # Lastly, escape any instances of || in the excerpt which Wikidot would translate into making a new column.
    tale['excerpt'] = tale['excerpt'].replace("||", "@<||>@")

    # We're going to use the same format whether or not there is attribution metadata.
    if tale['created_by'] is None:
        tale['attributions'] = '(account deleted)'
        tale['created_by'] = '(account deleted)'
    else:
        tale['attributions'] = '[[user ' + tale['created_by'] + ']] (author)'

    # These will be a temp holding variable.
    attribs = []
    authors = []

    # Check the attribution-metadata page first. Look for a cell with a string matching our tale's fullname.
    needle = a.find_all("td", string=tale['fullname'])
    # if there are one or more matches, build tale['attributions']
    for match in needle:
        # The next sibling of the match will be the username.
        attr_user = match.find_next_sibling("td")
        # The one after that will be the credit type.
        attr_type = attr_user.find_next_sibling("td").get_text()
        # Use get_text() to remove the <td> tags.
        attr_user = attr_user.get_text()
        # Append it to the list.
        attribs.append("[[user " + attr_user + "]] (" + attr_type + ") _\n")
        authors.append(attr_user)

    # Make a string if we had any work to do in attribution metadata and overwrite attributions.
    if len(attribs) > 0:
        tale['attributions'] = ''.join(attribs)
        # Make note of this tale because we're going to handle it differently in author sorting.
        tale['has_attribution_metadata'] = True
        tale['attribution_authors'] = authors

    # Remove the line-break from the last attributed person if it exists.
    if tale['attributions'][-3:] is '_\n':
        tale['attributions'] = tale['attributions'][0:-3]


# Tales by Title

# Index is used as a combination Table of Contents and way to organize the dicts we break tales into.
index = ['Misc','A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']

for character in index:
    t_alpha[character] = ["[[# " + character + "]]\n[[div class=\"section\"]]\n+++ " + character + "\n[#top ⇑]\n||~ Title||~ Author||~ Created||\n"]

for tale in t:
    # Build the table, row by row with title, author/attributions, created date, and excerpt.
    row = '||[[[' + tale['fullname'] + '|]]]||' + tale['attributions'] + '||//' + tale['created_at'][:10]\
          + '//||\n||||||' + tale['excerpt'] + '||\n'
    try:
        if tale['title'][:1] in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
            t_alpha[tale['title'][:1].upper()].append(row.encode("UTF-8"))
        else:
            t_alpha['Misc'].append(row.encode("UTF-8"))
    except KeyError:
        continue

# Close out the div we opened for each group.
for character in index:
    t_alpha[character].append('[[/div]]\n')

# We've done all our prep, let's get Tales By Title.
process_output(t_alpha, "tales-by-title")

# We'll handle author sort slightly differently using attribution metadata.
t = sorted(t, key=lambda x: x['created_by'].lower())

for character in index:
    t_author[character] = ["[[# " + character + "]]\n[[div class=\"section\"]]\n+++ " + character + "\n[#top ⇑]\n||~ Title||~ Author||~ Created||\n"]

for tale in t:
    # Build the table, row by row with title, author/attributions, created date, and excerpt.
    row = '||[[[' + tale['fullname'] + '|]]]||' + tale['attributions'] + '||//' + tale['created_at'][:10]\
          + '//||\n||||||' + tale['excerpt'] + '||\n'

    # If there are multiple authors, give them each their own credit in the list.
    if 'has_attribution_metadata' in tale:
        for author in tale['attribution_authors']:
            try:
                if author[:1] in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
                    t_author[author[:1].upper()].append(row.encode("UTF-8"))
                else:
                    t_author['Misc'].append(row.encode("UTF-8"))
            except KeyError:
                continue
    # Otherwise we handle it the same way as tales-by-title.
    else:
        try:
            if tale['created_by'][:1] in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
                t_author[tale['created_by'][:1].upper()].append(row.encode("UTF-8"))
            else:
                t_author['Misc'].append(row.encode("UTF-8"))
        except KeyError:
            continue

# Close out the div we opened for each group.
for character in index:
    t_author[character].append('[[/div]]\n')

# We've done all our prep, let's get Tales By Author.
process_output(t_author, "tales-by-author")

# Tales By Date
# Rather than a precomputed index, we'll use the first 7 characters of created_at and do it that way.

for tale in t:
    # Build the table, row by row with title, author/attributions, created date, and excerpt.
    row = '||[[[' + tale['fullname'] + '|]]]||' + tale['attributions'] + '||//' + tale['created_at'][:10]\
          + '//||\n||||||' + tale['excerpt'] + '||\n'

    try:

        if tale['created_at'][:7] in t_date:
            # We've already got a list for this month, just add the row.
            t_date[tale['created_at'][:7]].append(row.encode("UTF-8"))
        else:
            # Put the header in, and then add the row.
            t_date[tale['created_at'][:7]] = ["[[# " + tale['created_at'][:7] + "]]\n[[div class=\"section\"]]\n+++ " + month_name[int(tale['created_at'][5:7])] + " " + tale['created_at'][:4] + "\n[#top ⇑]\n||~ Title||~ Author||~ Created||\n"]
            t_date[tale['created_at'][:7]].append(row.encode("UTF-8"))
    except KeyError:
        continue

# Close our divs.
for item in t_date:
    t_date[item].append('[[/div]]\n')

# Our usual sorting method doesn't work for dates, we need to force some order on the list.
t_date_sorted = OrderedDict(sorted(t_date.items(), key=lambda x: x[0]))

# We've done all our prep, let's get Tales By Date.
process_output(t_date_sorted, "tales-by-date")
