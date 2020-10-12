# Fuzzaide
## Tools
Most of these tools were born due to extraordinary laziness of their author. Tools are 'probably' not production ready yet.
### appverif_export_all.au3
This AutoIt script can be used with Application Verifier to export ALL available execution logs to some directory (**this was only tested on appverif version 10.0 x64 running on Windows 10 x64**).<br>
Application Verifier (appverif) is a Windows-specific program from Microsoft used to sanitize programs on the fly with different checks to detect misuse of memory handling functions and whole bunch of other things. Its intended use is to launch tested application under WinDBG and manually inspect the issues, but Application Verifier also saves some run information as ".dat" binary files. User can then extract stack traces from crashing runs recorded in ".dat" files (export to XML files) manually one by one.<br>
Unfortunately Application Verifier does not provide a way to export all the logs at once. This script automates appverif UI to enumerate all the log entries and export each one of them as XML file.<br>
How to use this script:
1. Add your tested program to Application Verifier.
2. Run the program with all the test cases you need, how many times you want.
3. Application Verifier logs should now contain some entries (crashing ones will probably be marked with numbers in "Error" column).
4. Run this AutoIt script from **elevated** command prompt: `AutoIt3_x64.exe .\appverif_export_all.au3 C:\appverif_logs_xml`
5. You should see blinking "Export Log" dialog window. By the end of script run, your directory should contain ".dat.xml" files.
### appverif_minimize.py
This Python script minimizes WinAFL crashes with help of Application Verifier XML log files containing stack traces. (**this was only tested on appverif version 10.0 x64 running on Windows 10 x64**)<br>
It can also minimize Application Verifier XML log files if you don't have/need case files.<br>
IDs of log files and crashing test cases should correspond because **this script relies on ID numbers used in names**.<br>
How to use this script:
1. Add your tested program to Application Verifier. **Clean previous run logs.**
2. Run the program with each WinAFL test case using command like this: <br>
`PS > Get-ChildItem -File -Path '.\out\crashes\*' -Include 'id*' | ForEach { Write-Output $_.fullname ; .\myapp.exe /file $_.fullname }` <br>
Ensure that test cases are executed in correct (ascending) order: id 0, then id 1, etc.
3. Export XML logs from Application Verifier (if you have 50+ files consider using tools like appverif_export_all.au3, see above).
4. Run appverif_minimize.py:
```
.\appverif_minimize.py --logs-in .\appverif_xml_logs --cases-in .\out\crashes --logs-out .\avmin\logs --cases-out .\avmin\cases
```
You can also see which of your cases produce same stack traces (add `-v` or omit `--logs-out` and `--cases-out`):
```
.\appverif_minimize.py --logs-in .\appverif_xml_logs --cases-in .\out\crashes # only printed
.\appverif_minimize.py --logs-in .\appverif_xml_logs --cases-in .\out\crashes -v --logs-out .\avmin\logs --cases-out .\avmin\crashes # printed and saved
```
If you don't need logs or crashes saved, just don't specify respective arguments:
```
.\appverif_minimize.py --logs-in .\appverif_xml_logs --cases-in .\out\crashes --cases-out .\avmin # save minimized cases, don't save logs
```
BTW `--cases-out` and `--logs-out` can point to the same directory if you like it.<br>
You can also minimize AppVerifier XML log files without having case files:
```
.\appverif_minimize.py --logs-in .\appverif_xml_logs --logs-out .\avmin
```
How it works: stack traces are extracted from XML logs; files sharing same stack traces are grouped together; case files are matched to XML files by ID numbers in their names. The script will surely mess up if you don't clean AppVerifier logs before running your test cases or if case / log file names were changed from original names given by WinAFL / Application Verifier.<br><br>
**TODO:** add severity filter (Error, Warning).
### argv-fuzz-cook.py
This Python script prepares test cases for fuzzing command line arguments with use of argv-fuzz-inl.h file from AFL repository. This is done by inserting \x00 between arguments and \x00\x00 in the end of arguments list and outputting it in binary format suitable for writing directly to file or passing to fuzzed program via stdin.<br>
How to use this script:
1. Find out correct command line for fuzzed application.<br>Let's say your app is "myapp" in current directory and it accepts argument "--check-all".
2. Pass program arguments to argv-fuzz-cook.py like this: `./argv-fuzz-cook.py ./myapp --check-all`
3. If you need it to be saved in file:  `./argv-fuzz-cook.py ./myapp --check-all > in/1`
4. If you need C-string representation: `./argv-fuzz-cook.py -c ./myapp --check-all`
### dupmanage.py
This Python script is in half-abandoned half-unfinished state. Its final purpose is to manage groups of duplicate files, for example extract only files with unique contents from some wildcarded path. As of now it only forms and shows groups of files with duplicate contents.
### fuzzman.py
This Python script automates running multiple instances of AFL-like fuzzers and has ability to stop them in case of not discovering new paths for certain amount of time. <br>
Invocation examples: <br>
Fuzz ./myapp using all CPU cores until stopped by Ctrl+C: <br>
	`fuzzman.py ./myapp` <br>
This uses ./in and ./out as input/output directories. If input directory doesn't exist, it will be created with simple initial corpus. <br>
Run 4 instances and specify in/out directories: <br>
	`fuzzman.py -n 4 -i ../inputs/for_myapp -o ../outputs/myapp ./myapp @@` <br>
Set memory limit of 10 kilobytes, cleanup output directory before starting: <br>
	`fuzzman.py -m 10K -C ./myapp` <br>
Pass additional agruments to fuzzer: <br>
	`fuzzman.py --more-args "-p fast" ./myapp @@` <br>
Specify non-default fuzzer (it should follow same command syntax as AFL): <br>
	`fuzzman.py --fuzzer-binary ~/git/fuzzer/obliterator ./myapp` <br>
Specify non-default fuzzer in PATH: <br>
	`fuzzman.py --fuzzer-binary obliterator ./myapp` <br>
Stop if there were no new paths (across all fuzzers) in 1 hour and 5 minutes: <br>
	`fuzzman.py --no-paths-stop "1 hrs, 5 min" ./myapp` <br>
Same as in previous example: <br>
	`fuzzman.py --no-paths-stop "1 hrs, 5" ./myapp` <br>
Same as in previous example, time measured in seconds: <br>
	`fuzzman.py --no-paths-stop 3900 ./myapp` <br>
fuzzman.py was developed for use with (and tested on) AFL++.
<br>
### split-dir-contents.py
This Python script may be used to "split" given directory into multiple directories by copying/moving files. For example, let's say some tool can only work with up to 100 files, otherwise it hangs.<br>
In this case you can invoke split-dir-contents.py as follows:<br>
```
./split-dir-contents.py -i myfiles -o splitted -n 100
```
If directory 'myfiles' contains 950 files you'll end up with 10 directories named splitted0 - splitted9 each containing not more than 100 files (directory splitted9 will contain 50 files).<br>
### split-file-contents.py
This Python script splits one file into few files to create samples for reproducing crashes/hangs. This is useful when tested application reads input from many files, but you have implemented fuzzing harness to read inputs from one fuzzed file to simultaneously fuzz multiple files.<br>
Two modes of splitting are implemented: split input file equally (exact naming of output files supported) or split input file to chunks of not more than size specified.<br>
Invocation example:
```
./split-file-contents.py -i crashcase -e 2 --names "player.dxt,player.obj" -o reproduce
```
This will equally split file 'crashcase' into two files, file 'reproduce/player.dxt' will contain the first half of file 'crashcase' and 'reproduce/player.obj' will contain the second half.<br>
Of course **it is assumed that your fuzzing harness splits input file in the same manner**.<br>
See --help for more info and check script code to see how it exactly works.
