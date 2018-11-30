// $BACKGROUND$

image frame = realimage("",4,512,512)
number num = 1
frame.setname("Random stream")

showimage(frame)

while ( !ShiftDown() )
{
	//frame = random()
	frame = num
	if ( num > 255 ) num = 0
	sleep(0.5)
	num += 1 
}

hideimage(frame)
Result("End: " + num + "\n")
