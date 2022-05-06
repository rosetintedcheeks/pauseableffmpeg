import subprocess
import sys
import os

'''
Spilts a files into segments and encodes those segments seperately using ffmpeg. Can be resumed without redoing the entire encode
'''
inputFile = os.path.basename(sys.argv[len(sys.argv) - 1])
args = ["ffmpeg", "-i", inputFile]
twoPass = True
if not twoPass:
    encodeArgs = [
        "-y",
        "-c:v", "hevc",
        "-crf:v", "23",
        "-pix_fmt", "yuv420p10le",
        "-preset:v", "slower",
        "-c:a", "copy", 
        "-map", "0:v",
        "-map", "0:a",
        "-f", "matroska"
    ]
else:
    firstEncodeArgs = [
        "-y",
        "-c:v", "libvpx-vp9",
        "-crf:v", "30",
        "-b:v", "0",
        "-pass", "1",
        "-an",
        "-pix_fmt", "yuv420p10le",
        "-f", "null",
    ]
    secondEncodeArgs = [
        "-y",
        "-c:v", "libvpx-vp9",
        "-crf:v", "30",
        "-b:v", "0",
        "-row-mt", "1",
        "-tiles", "4x4",
        "-pass", "2",
        "-pix_fmt", "yuv420p10le",
        "-c:a", "libopus", 
        "-map", "0:v",
        "-map", "0:a",
        "-f", "webm"
    ]
segmentLocation = os.path.expanduser("~/share/sugment/")
markerFile = os.path.expanduser("~/share/resume.txt")
newSegmentLocation = os.path.expanduser("~/share/new-sugment/")
os.chdir(os.path.expanduser("~/share"))

def ffmpegSegment(args, inputFile, segmentLocation):
    print("Segmenting file...")
    segmentArgs = [
        "-c", "copy", 
        "-flags", "+global_header", 
        "-f", "segment",
    ]
    for a in segmentArgs:
        args.append(a)

    # result will be file.ext => file.0000.ext
    filePath = inputFile.split(".")
    filePath.insert(len(filePath) - 1, "%04d")
    segmentedFilePath = ".".join(filePath)

    args.append(segmentLocation + segmentedFilePath)

    #TODO: check for errors
    subprocess.run(args)

def ffmpegEncodeSegments(segment, args, encodeArgs, inputFile, segmentLocation, marker, outputFile=None, outputExtension="mkv"):
    totalSegments = countSegments(segmentLocation)
    writeMarker(marker, segment)
    segmentArgs = args.copy()
    completedPercentage = (segment / totalSegments) * 100
    if outputFile is not None:
        print("Encoding segment #" + f"{segment+1:04d}" + " out of " + f"{totalSegments:04d}" + " (" + f"{completedPercentage:.2f}" + "%)")
    for a in encodeArgs:
        segmentArgs.append(a)

    # result will be file.ext => file.0000.ext
    filePath = inputFile.split(".")
    filePath.insert(len(filePath) - 1, f"{segment:04d}")
    segmentInputFile = '.'.join(filePath)

    # changing the input file to the selected segment
    segmentArgs[2] = segmentLocation + segmentInputFile

    if outputFile is None:
        # change output file's extension to outputExtension (default mkv)
        filePath[len(filePath) - 1] = outputExtension
        segmentOutputFile = newSegmentLocation + '.'.join(filePath)
    else:
        segmentOutputFile = outputFile


    segmentArgs.append(segmentOutputFile)

    try:
        subprocess.run(segmentArgs, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        exit("ffmpeg call failed while encoding segments")

def ffmpegTwoPassEncodeSegments(segment, args, encodeArgs, inputFile, segmentLocation, marker):
    ffmpegEncodeSegments(segment, args.copy(), encodeArgs[0], inputFile, segmentLocation, marker, outputFile="/dev/null")
    ffmpegEncodeSegments(segment, args.copy(), encodeArgs[1], inputFile, segmentLocation, marker, outputExtension="webm")

def ffmpegReconnectSegments(args, inputFile, segmentLocation, newSegmentLocation):
    reconnectFileName = newSegmentLocation + "reconnect.ffconcat"
    with open(reconnectFileName, "w") as reconnectFile:
        nslList = os.listdir(newSegmentLocation)
        nslList.sort()
        for file in nslList:
            if file == "reconnect.ffconcat":
                continue
            reconnectFile.write("file " + 
            file
            .replace("'", "\\'") # escape '
            .replace(" ", "\\ ") # escape space
             + "\n")
    outputFile = inputFile.split(".")
    outputFile[len(outputFile) - 1] = "mkv"
    outputFile = '.'.join(outputFile)
    tmpArgs = [
        args[0],
        "-f", "concat",
        "-safe", "0",
        "-i", reconnectFileName,
        "-c", "copy",
        "-fflags", "+genpts",
        "-f", "matroska",
        outputFile
    ]
    for file in os.listdir(segmentLocation):
        os.remove(os.path.abspath(segmentLocation + file))
    subprocess.run(tmpArgs)
    #scary
    #for file in os.listdir(newSegmentLocation):
    #    os.remove(os.path.abspath(newSegmentLocation + file))

def countSegments(segmentLocation):
    return len(os.listdir(segmentLocation))

def writeMarker(marker, segment):
    marker.seek(0)
    marker.truncate()
    marker.write(str(segment))
    marker.flush()

def readMarker(marker):
    marker.seek(0)
    return int(marker.read())


if __name__ == "__main__":
    marker = open(markerFile, "r+")

    if "--resume" not in sys.argv:
        if countSegments(segmentLocation) != 0:
            answer = input("There are files in the segment location. Delete them? [y/N] ")
            if answer != "y" and answer != "Y":
                exit("Need segment location empty unless we are resuming")
            else:
                for file in os.listdir(segmentLocation):
                    os.remove(os.path.abspath(segmentLocation + file))
                for file in os.listdir(newSegmentLocation):
                    os.remove(os.path.abspath(newSegmentLocation + file))
        # segmenting
        ffmpegSegment(args.copy(), inputFile, segmentLocation)
        writeMarker(marker, 0)

    print("Encoding segments...")
    for segment in range(readMarker(marker), countSegments(segmentLocation)):
        if twoPass:
            encodeArgs = [firstEncodeArgs.copy(), secondEncodeArgs.copy()]
            ffmpegTwoPassEncodeSegments(segment, args.copy(), encodeArgs, inputFile, segmentLocation, marker)
        else:
            ffmpegEncodeSegments(segment, args.copy(), encodeArgs.copy(), inputFile, segmentLocation, marker)
    ffmpegReconnectSegments(args.copy(), inputFile, segmentLocation, newSegmentLocation)
    marker.close()
