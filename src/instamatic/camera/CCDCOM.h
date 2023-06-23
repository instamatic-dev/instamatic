 int initCCDCOM(int nNumber);
 void releaseCCDCOM(void);

//Whether the camera reports its name and sizes
 bool isCameraInfoAvailable();

 bool cameraName(wchar_t* wcName, int wcNameSize);
 bool cameraDimensions(int* pnWidth, int* pnHeight);
 int cameraCount(void);

 int execScript(const wchar_t* script);

 int acquireImageNewInt(int area_t, int area_l, int area_b, int area_r,
							   int* pdata, int* pnImgWidth, int* pnImgHeight, int nBinning, double fExposure, bool bShowInDM);
 int acquireImageNewFloat(int area_t, int area_l, int area_b, int area_r, int nBinning, double fExposure, bool bShowInDM,	//Input parameters
								float** pdata, int* pnImgWidth, int* pnImgHeight	//Output parameters
								);

 void CCDCOM2_release(float* pdata);


// Example code:

//Initialization. 20120101 is a magic number. result = 1 on successful return.
int result = initCCDCOM(20120101);

//pdata is a pointer to a pointer pointing the data. Memory is allocated and returned by the function and needs to be freed outside. See below
result = acquireImageNewFloat(0, 0, 2048, 2048, 1, 0.5, false, &pdata, &pnWidth, &pnHeight);

//Free the memory returned by the previous function call
CCDCOM2_release(pdata);

//Close dll.
releaseCCDCOM();
