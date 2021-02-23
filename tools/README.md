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

### appverif-minimize.py
This Python script minimizes WinAFL crashes with help of Application Verifier XML log files containing stack traces. (**this was only tested on appverif version 10.0 x64 running on Windows 10 x64**)<br>
It can also minimize Application Verifier XML log files if you don't have/need case files.<br>
IDs of log files and crashing test cases should correspond because **this script relies on ID numbers used in names**.<br>
How to use this script:
1. Add your tested program to Application Verifier. **Clean previous run logs.**
2. Run the program with each WinAFL test case using command like this: <br>
`PS > Get-ChildItem -File -Path '.\out\crashes\*' -Include 'id*' | ForEach { Write-Output $_.fullname ; .\myapp.exe /file $_.fullname }` <br>
Ensure that test cases are executed in correct (ascending) order: id 0, then id 1, etc.
3. Export XML logs from Application Verifier (if you have 50+ files consider using tools like appverif_export_all.au3, see above).
4. Run appverif-minimize.py:
```
.\appverif-minimize.py --logs-in .\appverif_xml_logs --cases-in .\out\crashes --logs-out .\avmin\logs --cases-out .\avmin\cases
```
You can also see which of your cases produce same stack traces (add `-v` or omit `--logs-out` and `--cases-out`):
```
.\appverif-minimize.py --logs-in .\appverif_xml_logs --cases-in .\out\crashes # only printed
.\appverif-minimize.py --logs-in .\appverif_xml_logs --cases-in .\out\crashes -v --logs-out .\avmin\logs --cases-out .\avmin\crashes # printed and saved
```
If you don't need logs or crashes saved, just don't specify respective arguments:
```
.\appverif-minimize.py --logs-in .\appverif_xml_logs --cases-in .\out\crashes --cases-out .\avmin # save minimized cases, don't save logs
```
BTW `--cases-out` and `--logs-out` can point to the same directory if you like it.<br>
You can also minimize AppVerifier XML log files without having case files:
```
.\appverif-minimize.py --logs-in .\appverif_xml_logs --logs-out .\avmin
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
This Python script is able manage groups of duplicate files, for example extract only files with unique contents from some wildcarded path(s). Supported actions: list, copy, move, delete. Supported filters: unique (ONLY work on files with unique contents), duplicates (ONLY work on files with non-unique contents), mixed (work on BOTH unique and duplicate files, but don't include more than one file with same contents). Mixed mode results in unique files in output directory. <br>
Invocation examples: <br>
Copy all test cases without making redundant duplicates, appending (`-a`) testcases dir (e.g. for next fuzzing job or to check coverage): <br>
	`dupmanage.py copy mixed "out/*/queue/id*" -a -o testcases` <br>
or, if you like: <br>
	`dupmanage.py copy mixed "out/*/queue/id*" "out/*/hangs/id*" "out/*/crashes/id*" -a -o testcases` <br>
Append option (`-a/--append`) makes sure to not make duplicates in output directory.<br>
Copy and move actions will store matching files in output directory with changed names. By default names will be "1", "2", "3", etc. You can use -P to preserve original names (this may overwrite files if there are matching names) or you can provide `--prefix`, `--suffix` and `--ext` to generate names like "sample1ftp.pcap", "sample2ftp.pcap" and so on. The latter method is preffered as it searches for the next available name and thus does not overwrite files.<br>
Hash all files with contents appearing EXACTLY ONCE in ./input_dir without checking inner directories: <br>
	`dupmanage.py list unique ./input_dir -s` <br>
Default hash function is sha1. Use `-L` to see available hash functions and `-H` to specify hash function. <br>
List duplicates in multiple directories (recursively traversing each one): <br>
	`dupmanage.py -R list duplicates in1 in2 in3` <br>
Dry-run option supported (`-D`) to emulate write operations and see what would happen during normal run.<br>
Some shorthands for commands are supported: `duplicates` = `dup`, `list` = `ls`, etc.<br>
### dupmanage FAQ
Q: **How many input directories are supported at most?** <br>
A: This is usually limited by available RAM and the user's patience. <br>

Q: **Script exits with error message like "incorrect action" or "incorrect input type" or "no output dir specified". What do I do?** <br>
A: Probably you don't follow correct order of positional arguments or mix and match order of positional and optional ones. <br>
Good examples that will work: `dupmanage.py -v -s ls dup "in/*" "in2/*"` or `dupmanage.py -vs ls dup "in/*" "in2/*" -R` <br>
Bad examples that will not work: `dupmanage.py ls -v dup "in/*"`, `dupmanage.py ls dup -R "in/*"` or `dupmanage.py ls dup "in/*" -s "in2/*"`. <br>
Simply put, always make sure that action, type of input files and input dirs come in a row. Optional args may be put before and/or after positional args and input directories. <br>

Q: **Should I quote input pattern(s)?** <br>
A: If you have many input files, yes. In other cases you may leave pattern matching to your shell. <br>

Q: **Why use "mixed" instead of "unique"? I wan't unique files in result!**<br>
A: When running dupmanage you're NOT asking for the RESULT to consist of UNIQUE files, you're telling dupmanage to process UNIQUE INPUT files.<br>
More explanation: "unique" type works on input files that don't have any copies. This means file with such contents (hash sum) should only appear once. If two files share the same hash sum, then both files are considered duplicates in terms of this script. "Mixed" type takes both unique and duplicate files but eliminates redundant duplicates: unique files are processed as is, but only one file in group of duplicates gets processed. <br>

Q: **Are there any use cases apart from storing fuzzing samples?** <br>
A: Why yes! You can search for duplicate junk like copied documents or media files, but beware: script doesn't check names or timestamps of input files. <br><br>

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
	`fuzzman.py --fuzzer-binary py-afl-fuzz ./myapp` <br>
Stop if there were no new paths (across all fuzzers) in 1 hour and 5 minutes: <br>
	`fuzzman.py --no-paths-stop "1 hrs, 5 min" ./myapp` <br>
Same as in previous example: <br>
	`fuzzman.py --no-paths-stop "1 hrs, 5" ./myapp` <br>
Same as in previous example, time measured in seconds: <br>
	`fuzzman.py --no-paths-stop 3900 ./myapp` <br>
fuzzman.py was developed for use with (and tested on) AFL++.
<br>

### fuzzman FAQ
Q: **Why?** <br>
A: I am too lazy to run same commands by hand, especially on many available cores. Yes, there are many tools to automate running many AFL instances, but I also wanted specific features: dynamic status screens changing by themselves, terminating fuzzing job if there were no new execution paths in e.g. 1 day. <br>

Q: **Does it work with WinAFL?** <br>
A: Yes. Well, kind of. It's a bit tricky, but possible: don't use Windows style slashes because it seem to drive subprocess.Popen crazy. <br>
Example in PowerShell (keep in mind that you are not limited to using absolute paths): <br>
```
PS > ./fuzzman.py -i D:/fuzz/in -o D:/fuzz/out --fuzzer-binary D:/WinAFL/bin64/afl-fuzz.exe -P --more-args "-t 5000 -D D:/DynRIO/bin64/ -- -coverage_module 7z.exe -coverage_module 7z.dll -target_module 7z.exe -target_offset 0x4853C -nargs 2 -fuzz_iterations 1000" D:/fuzz/7-Zip/7z.exe t '@@'
```
*At this moment WinAFL support is very limited: status screen looks 'not OK' and you can't even expect a proper exit with Ctrl+C, in fact you will probably have to kill remaining processes via Task Manager :(* <br>

Q: **Fuzzman exits because all instances failed to start. How to fix???** <br>
A: Please try starting one AFL instance to inspect error message (by copying one of the commands kindly provided by fuzzman). Probably you need to run `afl-system-config` or something. <br>

Q: **What happens if some fuzzer instance will stop working?** <br>
A: Fuzzman will restart dead fuzzer processes on its own. If restarted instance doesn't start working (several times in a row), fuzzman will stop trying to restart it. <br><br>


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
