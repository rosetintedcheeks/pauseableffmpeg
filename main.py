from ast import arg
import subprocess
import sys
import os

'''
Spilts a files into segments and encodes those segments seperately using ffmpeg. Can be resumed without redoing the entire encode
'''
inputFile = os.path.basename(sys.argv[len(sys.argv) - 1])
args = ["ffmpeg", "-i", inputFile]
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
segmentLocation = os.path.expanduser("~/fast/sugment/")
markerFile = os.path.expanduser("~/fast/resume.txt")
newSegmentLocation = os.path.expanduser("~/fast/new-sugment/")
os.chdir(os.path.expanduser("~/fast"))

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

def ffmpegEncodeSegments(args, encodeArgs, inputFile, segmentLocation, marker):
    print("Encoding segments...")
    markerLocation = readMarker(marker)
    totalSegments = countSegments(segmentLocation)
    for segment in range(markerLocation, totalSegments):
        writeMarker(marker, segment)
        segmentArgs = args.copy()
        completedPercentage = (segment / totalSegments) * 100
        print("Encoding segment #" + f"{segment:04d}" + " out of " + f"{totalSegments:04d}" + " (" + f"{completedPercentage:.2f}" + "%)")
        for a in encodeArgs:
            segmentArgs.append(a)

        # result will be file.ext => file.0000.ext
        filePath = inputFile.split(".")
        filePath.insert(len(filePath) - 1, f"{segment:04d}")
        segmentInputFile = '.'.join(filePath)

        # changing the input file to the selected segment
        segmentArgs[2] = segmentLocation + segmentInputFile

        # use mkv ext on output
        filePath[len(filePath) - 1] = "mkv"
        segmentOutputFile = '.'.join(filePath)

        segmentArgs.append(newSegmentLocation + segmentOutputFile)

        try:
            subprocess.run(segmentArgs, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            exit("ffmpeg call failed while encoding segments")

def ffmpegReconnectSegments(args, inputFile, newSegmentLocation):
    reconnectFileName = newSegmentLocation + "reconnect.ffconcat"
    with open(reconnectFileName, "w") as reconnectFile:
        nslList = os.listdir(newSegmentLocation)
        nslList.sort()
        for file in nslList:
            if file == "reconnect.ffconcat":
                continue
            reconnectFile.write("file " + file + "\n")
    outputFile = inputFile.split(".")
    outputFile[len(outputFile) - 1] = "mkv"
    outputFile = '.'.join(outputFile)
    tmpArgs = [
        args[0],
        "-f", "concat",
        "-i", reconnectFileName,
        "-c", "copy",
        "-fflags", "+genpts",
        "-f", "matroska",
        outputFile
    ]
    subprocess.run(tmpArgs)

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
        ffmpegSegment(args.copy(), inputFile, segmentLocation, newSegmentLocation)
        writeMarker(marker, 0)

    ffmpegEncodeSegments(args.copy(), encodeArgs.copy(), inputFile, segmentLocation, marker)
    ffmpegReconnectSegments(args.copy(), inputFile, newSegmentLocation)
    marker.close()
