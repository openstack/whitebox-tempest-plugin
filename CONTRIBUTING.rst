============
Contributing
============

This repo uses the standard Github Pull Request workflow to deal with
code contribution. This document provides a step by step description
of how to do this in order to simplify the review process. These steps
presuppose that you're a member of the RHOS-QE organization on Github
and that you've already `associated an SSH key to your account`_. If
you're not a member of the github organization, it's still possible to
contribute by forking the repo. See the last paragraph of this doc for
more info.

.. _associated an SSH key to your account: https://help.github.com/articles/adding-a-new-ssh-key-to-your-github-account/

1. If you haven't already, clone the plugin repository to your work
   machine. I recommend doing this over SSH.

::

   git clone git@github.com:RHOS-QE/RHOS-Tempest-Plugin

2. If you haven't done this in a while, make sure to pull all the
   latest changes to your master branch. Try to do this regularly so
   that you decrease the risk of encountering merge conflicts.

::

   git checkout master && git pull origin master

3. Create a new local branch. This step is important, your development
   should not happen on the master branch. Every change is committed
   on a separate branch and only merged in master after going through
   the review process. The name of your created branch should be as
   descriptive as possible to make it easier for the reviewer.

::

   git checkout -b my_super_new_feature

4. Make your modifications.

5. Run the `tox` job and make sure it succeeds. Your contribution
   won't be accepted if it fails these jobs.

::

   tox

6. Once you're satisfied with your changes and they pass the tox jobs,
   you are ready to commit them. When writing your commit message, try
   to keep the `OpenStack guidelines for commit messages`_ in mind.

.. _Openstack guidelines for commit messages: https://wiki.openstack.org/wiki/GitCommitMessages#Summary_of_Git_commit_message_structure

::

   git add files && git commit

7. You can now push your branch to the origin repository.

::

   git push -u origin my_super_new_feature

8. From the github web interface, you can now `initiate a Pull
   Request`_.

.. _initiate a Pull Request: https://help.github.com/articles/creating-a-pull-request/


If you're not a member of RHOS-QE
---------------------------------

If you're not a member of the organization, you won't have write
access to the github repository so you cannot upload your branches.
The way to deal with it is to use the github interface to fork the
repo to your account, then clone your own fork locally in step 1.

::

   git clone git@github.com:yourusername/RHOS-Tempest-Plugin

All the other steps described above are still valid and Github is fully
capable of handling a pull request coming from a fork of the repo.
