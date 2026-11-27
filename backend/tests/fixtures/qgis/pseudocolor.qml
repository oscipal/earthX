<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.4-Prizren" styleCategories="Symbology">
  <pipe-data-defined-properties>
    <Option type="Map">
      <Option value="" type="QString" name="name"/>
      <Option name="properties"/>
      <Option value="collection" type="QString" name="type"/>
    </Option>
  </pipe-data-defined-properties>
  <pipe>
    <provider>
      <resampling zoomedInResamplingMethod="nearestNeighbour" zoomedOutResamplingMethod="nearestNeighbour" enabled="false" maxOversampling="2"/>
    </provider>
    <rasterrenderer classificationMax="0.3" alphaBand="-1" classificationMin="0" nodataColor="" opacity="1" type="singlebandpseudocolor" band="1">
      <minMaxOrigin>
        <limits>None</limits>
        <extent>WholeRaster</extent>
        <statAccuracy>Estimated</statAccuracy>
        <cumulativeCutLower>0.02</cumulativeCutLower>
        <cumulativeCutUpper>0.98</cumulativeCutUpper>
        <stdDevFactor>2</stdDevFactor>
      </minMaxOrigin>
      <rastershader>
        <colorrampshader labelPrecision="6" maximumValue="0.29999999999999999" minimumValue="0" classificationMode="1" clip="0" colorRampType="INTERPOLATED">
          <colorramp type="gradient" name="[source]">
            <Option type="Map">
              <Option value="68,1,84,255" type="QString" name="color1"/>
              <Option value="253,231,36,255" type="QString" name="color2"/>
              <Option value="ccw" type="QString" name="direction"/>
              <Option value="0" type="QString" name="discrete"/>
              <Option value="gradient" type="QString" name="rampType"/>
              <Option value="rgb" type="QString" name="spec"/>
              <Option value="0.00392157;68,2,85,255;rgb;ccw:0.00784314;68,3,87,255;rgb;ccw:0.0117647;69,5,88,255;rgb;ccw:0.0156863;69,6,90,255;rgb;ccw:0.0196078;69,8,91,255;rgb;ccw:0.0235294;70,9,92,255;rgb;ccw:0.027451;70,11,94,255;rgb;ccw:0.0313725;70,12,95,255;rgb;ccw:0.0352941;70,14,97,255;rgb;ccw:0.0392157;71,15,98,255;rgb;ccw:0.0431373;71,17,99,255;rgb;ccw:0.0470588;71,18,101,255;rgb;ccw:0.0509804;71,20,102,255;rgb;ccw:0.054902;71,21,103,255;rgb;ccw:0.0588235;71,22,105,255;rgb;ccw:0.0627451;71,24,106,255;rgb;ccw:0.0666667;72,25,107,255;rgb;ccw:0.0705882;72,26,108,255;rgb;ccw:0.0745098;72,28,110,255;rgb;ccw:0.0784314;72,29,111,255;rgb;ccw:0.0823529;72,30,112,255;rgb;ccw:0.0862745;72,32,113,255;rgb;ccw:0.0901961;72,33,114,255;rgb;ccw:0.0941176;72,34,115,255;rgb;ccw:0.0980392;72,35,116,255;rgb;ccw:0.101961;71,37,117,255;rgb;ccw:0.105882;71,38,118,255;rgb;ccw:0.109804;71,39,119,255;rgb;ccw:0.113725;71,40,120,255;rgb;ccw:0.117647;71,42,121,255;rgb;ccw:0.121569;71,43,122,255;rgb;ccw:0.12549;71,44,123,255;rgb;ccw:0.129412;70,45,124,255;rgb;ccw:0.133333;70,47,124,255;rgb;ccw:0.137255;70,48,125,255;rgb;ccw:0.141176;70,49,126,255;rgb;ccw:0.145098;69,50,127,255;rgb;ccw:0.14902;69,52,127,255;rgb;ccw:0.152941;69,53,128,255;rgb;ccw:0.156863;69,54,129,255;rgb;ccw:0.160784;68,55,129,255;rgb;ccw:0.164706;68,57,130,255;rgb;ccw:0.168627;67,58,131,255;rgb;ccw:0.172549;67,59,131,255;rgb;ccw:0.176471;67,60,132,255;rgb;ccw:0.180392;66,61,132,255;rgb;ccw:0.184314;66,62,133,255;rgb;ccw:0.188235;66,64,133,255;rgb;ccw:0.192157;65,65,134,255;rgb;ccw:0.196078;65,66,134,255;rgb;ccw:0.2;64,67,135,255;rgb;ccw:0.203922;64,68,135,255;rgb;ccw:0.207843;63,69,135,255;rgb;ccw:0.211765;63,71,136,255;rgb;ccw:0.215686;62,72,136,255;rgb;ccw:0.219608;62,73,137,255;rgb;ccw:0.223529;61,74,137,255;rgb;ccw:0.227451;61,75,137,255;rgb;ccw:0.231373;61,76,137,255;rgb;ccw:0.235294;60,77,138,255;rgb;ccw:0.239216;60,78,138,255;rgb;ccw:0.243137;59,80,138,255;rgb;ccw:0.247059;59,81,138,255;rgb;ccw:0.25098;58,82,139,255;rgb;ccw:0.254902;58,83,139,255;rgb;ccw:0.258824;57,84,139,255;rgb;ccw:0.262745;57,85,139,255;rgb;ccw:0.266667;56,86,139,255;rgb;ccw:0.270588;56,87,140,255;rgb;ccw:0.27451;55,88,140,255;rgb;ccw:0.278431;55,89,140,255;rgb;ccw:0.282353;54,90,140,255;rgb;ccw:0.286275;54,91,140,255;rgb;ccw:0.290196;53,92,140,255;rgb;ccw:0.294118;53,93,140,255;rgb;ccw:0.298039;52,94,141,255;rgb;ccw:0.301961;52,95,141,255;rgb;ccw:0.305882;51,96,141,255;rgb;ccw:0.309804;51,97,141,255;rgb;ccw:0.313725;50,98,141,255;rgb;ccw:0.317647;50,99,141,255;rgb;ccw:0.321569;49,100,141,255;rgb;ccw:0.32549;49,101,141,255;rgb;ccw:0.329412;49,102,141,255;rgb;ccw:0.333333;48,103,141,255;rgb;ccw:0.337255;48,104,141,255;rgb;ccw:0.341176;47,105,141,255;rgb;ccw:0.345098;47,106,141,255;rgb;ccw:0.34902;46,107,142,255;rgb;ccw:0.352941;46,108,142,255;rgb;ccw:0.356863;46,109,142,255;rgb;ccw:0.360784;45,110,142,255;rgb;ccw:0.364706;45,111,142,255;rgb;ccw:0.368627;44,112,142,255;rgb;ccw:0.372549;44,113,142,255;rgb;ccw:0.376471;44,114,142,255;rgb;ccw:0.380392;43,115,142,255;rgb;ccw:0.384314;43,116,142,255;rgb;ccw:0.388235;42,117,142,255;rgb;ccw:0.392157;42,118,142,255;rgb;ccw:0.396078;42,119,142,255;rgb;ccw:0.4;41,120,142,255;rgb;ccw:0.403922;41,121,142,255;rgb;ccw:0.407843;40,122,142,255;rgb;ccw:0.411765;40,122,142,255;rgb;ccw:0.415686;40,123,142,255;rgb;ccw:0.419608;39,124,142,255;rgb;ccw:0.423529;39,125,142,255;rgb;ccw:0.427451;39,126,142,255;rgb;ccw:0.431373;38,127,142,255;rgb;ccw:0.435294;38,128,142,255;rgb;ccw:0.439216;38,129,142,255;rgb;ccw:0.443137;37,130,142,255;rgb;ccw:0.447059;37,131,141,255;rgb;ccw:0.45098;36,132,141,255;rgb;ccw:0.454902;36,133,141,255;rgb;ccw:0.458824;36,134,141,255;rgb;ccw:0.462745;35,135,141,255;rgb;ccw:0.466667;35,136,141,255;rgb;ccw:0.470588;35,137,141,255;rgb;ccw:0.47451;34,137,141,255;rgb;ccw:0.478431;34,138,141,255;rgb;ccw:0.482353;34,139,141,255;rgb;ccw:0.486275;33,140,141,255;rgb;ccw:0.490196;33,141,140,255;rgb;ccw:0.494118;33,142,140,255;rgb;ccw:0.498039;32,143,140,255;rgb;ccw:0.501961;32,144,140,255;rgb;ccw:0.505882;32,145,140,255;rgb;ccw:0.509804;31,146,140,255;rgb;ccw:0.513725;31,147,139,255;rgb;ccw:0.517647;31,148,139,255;rgb;ccw:0.521569;31,149,139,255;rgb;ccw:0.52549;31,150,139,255;rgb;ccw:0.529412;30,151,138,255;rgb;ccw:0.533333;30,152,138,255;rgb;ccw:0.537255;30,153,138,255;rgb;ccw:0.541176;30,153,138,255;rgb;ccw:0.545098;30,154,137,255;rgb;ccw:0.54902;30,155,137,255;rgb;ccw:0.552941;30,156,137,255;rgb;ccw:0.556863;30,157,136,255;rgb;ccw:0.560784;30,158,136,255;rgb;ccw:0.564706;30,159,136,255;rgb;ccw:0.568627;30,160,135,255;rgb;ccw:0.572549;31,161,135,255;rgb;ccw:0.576471;31,162,134,255;rgb;ccw:0.580392;31,163,134,255;rgb;ccw:0.584314;32,164,133,255;rgb;ccw:0.588235;32,165,133,255;rgb;ccw:0.592157;33,166,133,255;rgb;ccw:0.596078;33,167,132,255;rgb;ccw:0.6;34,167,132,255;rgb;ccw:0.603922;35,168,131,255;rgb;ccw:0.607843;35,169,130,255;rgb;ccw:0.611765;36,170,130,255;rgb;ccw:0.615686;37,171,129,255;rgb;ccw:0.619608;38,172,129,255;rgb;ccw:0.623529;39,173,128,255;rgb;ccw:0.627451;40,174,127,255;rgb;ccw:0.631373;41,175,127,255;rgb;ccw:0.635294;42,176,126,255;rgb;ccw:0.639216;43,177,125,255;rgb;ccw:0.643137;44,177,125,255;rgb;ccw:0.647059;46,178,124,255;rgb;ccw:0.65098;47,179,123,255;rgb;ccw:0.654902;48,180,122,255;rgb;ccw:0.658824;50,181,122,255;rgb;ccw:0.662745;51,182,121,255;rgb;ccw:0.666667;53,183,120,255;rgb;ccw:0.670588;54,184,119,255;rgb;ccw:0.67451;56,185,118,255;rgb;ccw:0.678431;57,185,118,255;rgb;ccw:0.682353;59,186,117,255;rgb;ccw:0.686275;61,187,116,255;rgb;ccw:0.690196;62,188,115,255;rgb;ccw:0.694118;64,189,114,255;rgb;ccw:0.698039;66,190,113,255;rgb;ccw:0.701961;68,190,112,255;rgb;ccw:0.705882;69,191,111,255;rgb;ccw:0.709804;71,192,110,255;rgb;ccw:0.713725;73,193,109,255;rgb;ccw:0.717647;75,194,108,255;rgb;ccw:0.721569;77,194,107,255;rgb;ccw:0.72549;79,195,105,255;rgb;ccw:0.729412;81,196,104,255;rgb;ccw:0.733333;83,197,103,255;rgb;ccw:0.737255;85,198,102,255;rgb;ccw:0.741176;87,198,101,255;rgb;ccw:0.745098;89,199,100,255;rgb;ccw:0.74902;91,200,98,255;rgb;ccw:0.752941;94,201,97,255;rgb;ccw:0.756863;96,201,96,255;rgb;ccw:0.760784;98,202,95,255;rgb;ccw:0.764706;100,203,93,255;rgb;ccw:0.768627;103,204,92,255;rgb;ccw:0.772549;105,204,91,255;rgb;ccw:0.776471;107,205,89,255;rgb;ccw:0.780392;109,206,88,255;rgb;ccw:0.784314;112,206,86,255;rgb;ccw:0.788235;114,207,85,255;rgb;ccw:0.792157;116,208,84,255;rgb;ccw:0.796078;119,208,82,255;rgb;ccw:0.8;121,209,81,255;rgb;ccw:0.803922;124,210,79,255;rgb;ccw:0.807843;126,210,78,255;rgb;ccw:0.811765;129,211,76,255;rgb;ccw:0.815686;131,211,75,255;rgb;ccw:0.819608;134,212,73,255;rgb;ccw:0.823529;136,213,71,255;rgb;ccw:0.827451;139,213,70,255;rgb;ccw:0.831373;141,214,68,255;rgb;ccw:0.835294;144,214,67,255;rgb;ccw:0.839216;146,215,65,255;rgb;ccw:0.843137;149,215,63,255;rgb;ccw:0.847059;151,216,62,255;rgb;ccw:0.85098;154,216,60,255;rgb;ccw:0.854902;157,217,58,255;rgb;ccw:0.858824;159,217,56,255;rgb;ccw:0.862745;162,218,55,255;rgb;ccw:0.866667;165,218,53,255;rgb;ccw:0.870588;167,219,51,255;rgb;ccw:0.87451;170,219,50,255;rgb;ccw:0.878431;173,220,48,255;rgb;ccw:0.882353;175,220,46,255;rgb;ccw:0.886275;178,221,44,255;rgb;ccw:0.890196;181,221,43,255;rgb;ccw:0.894118;183,221,41,255;rgb;ccw:0.898039;186,222,39,255;rgb;ccw:0.901961;189,222,38,255;rgb;ccw:0.905882;191,223,36,255;rgb;ccw:0.909804;194,223,34,255;rgb;ccw:0.913725;197,223,33,255;rgb;ccw:0.917647;199,224,31,255;rgb;ccw:0.921569;202,224,30,255;rgb;ccw:0.92549;205,224,29,255;rgb;ccw:0.929412;207,225,28,255;rgb;ccw:0.933333;210,225,27,255;rgb;ccw:0.937255;212,225,26,255;rgb;ccw:0.941176;215,226,25,255;rgb;ccw:0.945098;218,226,24,255;rgb;ccw:0.94902;220,226,24,255;rgb;ccw:0.952941;223,227,24,255;rgb;ccw:0.956863;225,227,24,255;rgb;ccw:0.960784;228,227,24,255;rgb;ccw:0.964706;231,228,25,255;rgb;ccw:0.968627;233,228,25,255;rgb;ccw:0.972549;236,228,26,255;rgb;ccw:0.976471;238,229,27,255;rgb;ccw:0.980392;241,229,28,255;rgb;ccw:0.984314;243,229,30,255;rgb;ccw:0.988235;246,230,31,255;rgb;ccw:0.992157;248,230,33,255;rgb;ccw:0.996078;250,230,34,255;rgb;ccw" type="QString" name="stops"/>
            </Option>
          </colorramp>
          <item value="0" color="#440154" alpha="255" label="0"/>
          <item value="0.00117647058823529" color="#440255" alpha="255" label="0.00117647"/>
          <item value="0.00235294117647059" color="#440357" alpha="255" label="0.00235294"/>
          <item value="0.00352941176470588" color="#450558" alpha="255" label="0.00352941"/>
          <item value="0.00470588235294118" color="#45065a" alpha="255" label="0.00470588"/>
          <item value="0.00588235294117647" color="#45085b" alpha="255" label="0.00588235"/>
          <item value="0.00705882352941176" color="#46095c" alpha="255" label="0.00705882"/>
          <item value="0.00823529411764706" color="#460b5e" alpha="255" label="0.00823529"/>
          <item value="0.00941176470588235" color="#460c5f" alpha="255" label="0.00941176"/>
          <item value="0.0105882352941176" color="#460e61" alpha="255" label="0.0105882"/>
          <item value="0.0117647058823529" color="#470f62" alpha="255" label="0.0117647"/>
          <item value="0.0129411764705882" color="#471163" alpha="255" label="0.0129412"/>
          <item value="0.0141176470588235" color="#471265" alpha="255" label="0.0141176"/>
          <item value="0.0152941176470588" color="#471466" alpha="255" label="0.0152941"/>
          <item value="0.0164705882352941" color="#471567" alpha="255" label="0.0164706"/>
          <item value="0.0176470588235294" color="#471669" alpha="255" label="0.0176471"/>
          <item value="0.0188235294117647" color="#47186a" alpha="255" label="0.0188235"/>
          <item value="0.02" color="#48196b" alpha="255" label="0.02"/>
          <item value="0.0211764705882353" color="#481a6c" alpha="255" label="0.0211765"/>
          <item value="0.0223529411764706" color="#481c6e" alpha="255" label="0.0223529"/>
          <item value="0.0235294117647059" color="#481d6f" alpha="255" label="0.0235294"/>
          <item value="0.0247058823529412" color="#481e70" alpha="255" label="0.0247059"/>
          <item value="0.0258823529411765" color="#482071" alpha="255" label="0.0258824"/>
          <item value="0.0270588235294118" color="#482172" alpha="255" label="0.0270588"/>
          <item value="0.0282352941176471" color="#482273" alpha="255" label="0.0282353"/>
          <item value="0.0294117647058824" color="#482374" alpha="255" label="0.0294118"/>
          <item value="0.0305882352941176" color="#472575" alpha="255" label="0.0305882"/>
          <item value="0.0317647058823529" color="#472676" alpha="255" label="0.0317647"/>
          <item value="0.0329411764705882" color="#472777" alpha="255" label="0.0329412"/>
          <item value="0.0341176470588235" color="#472878" alpha="255" label="0.0341176"/>
          <item value="0.0352941176470588" color="#472a79" alpha="255" label="0.0352941"/>
          <item value="0.0364705882352941" color="#472b7a" alpha="255" label="0.0364706"/>
          <item value="0.0376470588235294" color="#472c7b" alpha="255" label="0.0376471"/>
          <item value="0.0388235294117647" color="#462d7c" alpha="255" label="0.0388235"/>
          <item value="0.04" color="#462f7c" alpha="255" label="0.04"/>
          <item value="0.0411764705882353" color="#46307d" alpha="255" label="0.0411765"/>
          <item value="0.0423529411764706" color="#46317e" alpha="255" label="0.0423529"/>
          <item value="0.0435294117647059" color="#45327f" alpha="255" label="0.0435294"/>
          <item value="0.0447058823529412" color="#45347f" alpha="255" label="0.0447059"/>
          <item value="0.0458823529411765" color="#453580" alpha="255" label="0.0458824"/>
          <item value="0.0470588235294118" color="#453681" alpha="255" label="0.0470588"/>
          <item value="0.0482352941176471" color="#443781" alpha="255" label="0.0482353"/>
          <item value="0.0494117647058823" color="#443982" alpha="255" label="0.0494118"/>
          <item value="0.0505882352941176" color="#433a83" alpha="255" label="0.0505882"/>
          <item value="0.0517647058823529" color="#433b83" alpha="255" label="0.0517647"/>
          <item value="0.0529411764705882" color="#433c84" alpha="255" label="0.0529412"/>
          <item value="0.0541176470588235" color="#423d84" alpha="255" label="0.0541176"/>
          <item value="0.0552941176470588" color="#423e85" alpha="255" label="0.0552941"/>
          <item value="0.0564705882352941" color="#424085" alpha="255" label="0.0564706"/>
          <item value="0.0576470588235294" color="#414186" alpha="255" label="0.0576471"/>
          <item value="0.0588235294117647" color="#414286" alpha="255" label="0.0588235"/>
          <item value="0.06" color="#404387" alpha="255" label="0.06"/>
          <item value="0.0611764705882353" color="#404487" alpha="255" label="0.0611765"/>
          <item value="0.0623529411764706" color="#3f4587" alpha="255" label="0.0623529"/>
          <item value="0.0635294117647059" color="#3f4788" alpha="255" label="0.0635294"/>
          <item value="0.0647058823529412" color="#3e4888" alpha="255" label="0.0647059"/>
          <item value="0.0658823529411765" color="#3e4989" alpha="255" label="0.0658824"/>
          <item value="0.0670588235294118" color="#3d4a89" alpha="255" label="0.0670588"/>
          <item value="0.068235294117647" color="#3d4b89" alpha="255" label="0.0682353"/>
          <item value="0.0694117647058824" color="#3d4c89" alpha="255" label="0.0694118"/>
          <item value="0.0705882352941176" color="#3c4d8a" alpha="255" label="0.0705882"/>
          <item value="0.0717647058823529" color="#3c4e8a" alpha="255" label="0.0717647"/>
          <item value="0.0729411764705882" color="#3b508a" alpha="255" label="0.0729412"/>
          <item value="0.0741176470588235" color="#3b518a" alpha="255" label="0.0741176"/>
          <item value="0.0752941176470588" color="#3a528b" alpha="255" label="0.0752941"/>
          <item value="0.0764705882352941" color="#3a538b" alpha="255" label="0.0764706"/>
          <item value="0.0776470588235294" color="#39548b" alpha="255" label="0.0776471"/>
          <item value="0.0788235294117647" color="#39558b" alpha="255" label="0.0788235"/>
          <item value="0.08" color="#38568b" alpha="255" label="0.08"/>
          <item value="0.0811764705882353" color="#38578c" alpha="255" label="0.0811765"/>
          <item value="0.0823529411764706" color="#37588c" alpha="255" label="0.0823529"/>
          <item value="0.0835294117647059" color="#37598c" alpha="255" label="0.0835294"/>
          <item value="0.0847058823529412" color="#365a8c" alpha="255" label="0.0847059"/>
          <item value="0.0858823529411765" color="#365b8c" alpha="255" label="0.0858824"/>
          <item value="0.0870588235294118" color="#355c8c" alpha="255" label="0.0870588"/>
          <item value="0.0882352941176471" color="#355d8c" alpha="255" label="0.0882353"/>
          <item value="0.0894117647058824" color="#345e8d" alpha="255" label="0.0894118"/>
          <item value="0.0905882352941176" color="#345f8d" alpha="255" label="0.0905882"/>
          <item value="0.0917647058823529" color="#33608d" alpha="255" label="0.0917647"/>
          <item value="0.0929411764705882" color="#33618d" alpha="255" label="0.0929412"/>
          <item value="0.0941176470588235" color="#32628d" alpha="255" label="0.0941176"/>
          <item value="0.0952941176470588" color="#32638d" alpha="255" label="0.0952941"/>
          <item value="0.0964705882352941" color="#31648d" alpha="255" label="0.0964706"/>
          <item value="0.0976470588235294" color="#31658d" alpha="255" label="0.0976471"/>
          <item value="0.0988235294117647" color="#31668d" alpha="255" label="0.0988235"/>
          <item value="0.1" color="#30678d" alpha="255" label="0.1"/>
          <item value="0.101176470588235" color="#30688d" alpha="255" label="0.101176"/>
          <item value="0.102352941176471" color="#2f698d" alpha="255" label="0.102353"/>
          <item value="0.103529411764706" color="#2f6a8d" alpha="255" label="0.103529"/>
          <item value="0.104705882352941" color="#2e6b8e" alpha="255" label="0.104706"/>
          <item value="0.105882352941176" color="#2e6c8e" alpha="255" label="0.105882"/>
          <item value="0.107058823529412" color="#2e6d8e" alpha="255" label="0.107059"/>
          <item value="0.108235294117647" color="#2d6e8e" alpha="255" label="0.108235"/>
          <item value="0.109411764705882" color="#2d6f8e" alpha="255" label="0.109412"/>
          <item value="0.110588235294118" color="#2c708e" alpha="255" label="0.110588"/>
          <item value="0.111764705882353" color="#2c718e" alpha="255" label="0.111765"/>
          <item value="0.112941176470588" color="#2c728e" alpha="255" label="0.112941"/>
          <item value="0.114117647058824" color="#2b738e" alpha="255" label="0.114118"/>
          <item value="0.115294117647059" color="#2b748e" alpha="255" label="0.115294"/>
          <item value="0.116470588235294" color="#2a758e" alpha="255" label="0.116471"/>
          <item value="0.117647058823529" color="#2a768e" alpha="255" label="0.117647"/>
          <item value="0.118823529411765" color="#2a778e" alpha="255" label="0.118824"/>
          <item value="0.12" color="#29788e" alpha="255" label="0.12"/>
          <item value="0.121176470588235" color="#29798e" alpha="255" label="0.121176"/>
          <item value="0.122352941176471" color="#287a8e" alpha="255" label="0.122353"/>
          <item value="0.123529411764706" color="#287a8e" alpha="255" label="0.123529"/>
          <item value="0.124705882352941" color="#287b8e" alpha="255" label="0.124706"/>
          <item value="0.125882352941176" color="#277c8e" alpha="255" label="0.125882"/>
          <item value="0.127058823529412" color="#277d8e" alpha="255" label="0.127059"/>
          <item value="0.128235294117647" color="#277e8e" alpha="255" label="0.128235"/>
          <item value="0.129411764705882" color="#267f8e" alpha="255" label="0.129412"/>
          <item value="0.130588235294118" color="#26808e" alpha="255" label="0.130588"/>
          <item value="0.131764705882353" color="#26818e" alpha="255" label="0.131765"/>
          <item value="0.132941176470588" color="#25828e" alpha="255" label="0.132941"/>
          <item value="0.134117647058824" color="#25838d" alpha="255" label="0.134118"/>
          <item value="0.135294117647059" color="#24848d" alpha="255" label="0.135294"/>
          <item value="0.136470588235294" color="#24858d" alpha="255" label="0.136471"/>
          <item value="0.137647058823529" color="#24868d" alpha="255" label="0.137647"/>
          <item value="0.138823529411765" color="#23878d" alpha="255" label="0.138824"/>
          <item value="0.14" color="#23888d" alpha="255" label="0.14"/>
          <item value="0.141176470588235" color="#23898d" alpha="255" label="0.141176"/>
          <item value="0.142352941176471" color="#22898d" alpha="255" label="0.142353"/>
          <item value="0.143529411764706" color="#228a8d" alpha="255" label="0.143529"/>
          <item value="0.144705882352941" color="#228b8d" alpha="255" label="0.144706"/>
          <item value="0.145882352941176" color="#218c8d" alpha="255" label="0.145882"/>
          <item value="0.147058823529412" color="#218d8c" alpha="255" label="0.147059"/>
          <item value="0.148235294117647" color="#218e8c" alpha="255" label="0.148235"/>
          <item value="0.149411764705882" color="#208f8c" alpha="255" label="0.149412"/>
          <item value="0.150588235294118" color="#20908c" alpha="255" label="0.150588"/>
          <item value="0.151764705882353" color="#20918c" alpha="255" label="0.151765"/>
          <item value="0.152941176470588" color="#1f928c" alpha="255" label="0.152941"/>
          <item value="0.154117647058824" color="#1f938b" alpha="255" label="0.154118"/>
          <item value="0.155294117647059" color="#1f948b" alpha="255" label="0.155294"/>
          <item value="0.156470588235294" color="#1f958b" alpha="255" label="0.156471"/>
          <item value="0.157647058823529" color="#1f968b" alpha="255" label="0.157647"/>
          <item value="0.158823529411765" color="#1e978a" alpha="255" label="0.158824"/>
          <item value="0.16" color="#1e988a" alpha="255" label="0.16"/>
          <item value="0.161176470588235" color="#1e998a" alpha="255" label="0.161176"/>
          <item value="0.162352941176471" color="#1e998a" alpha="255" label="0.162353"/>
          <item value="0.163529411764706" color="#1e9a89" alpha="255" label="0.163529"/>
          <item value="0.164705882352941" color="#1e9b89" alpha="255" label="0.164706"/>
          <item value="0.165882352941176" color="#1e9c89" alpha="255" label="0.165882"/>
          <item value="0.167058823529412" color="#1e9d88" alpha="255" label="0.167059"/>
          <item value="0.168235294117647" color="#1e9e88" alpha="255" label="0.168235"/>
          <item value="0.169411764705882" color="#1e9f88" alpha="255" label="0.169412"/>
          <item value="0.170588235294118" color="#1ea087" alpha="255" label="0.170588"/>
          <item value="0.171764705882353" color="#1fa187" alpha="255" label="0.171765"/>
          <item value="0.172941176470588" color="#1fa286" alpha="255" label="0.172941"/>
          <item value="0.174117647058824" color="#1fa386" alpha="255" label="0.174118"/>
          <item value="0.175294117647059" color="#20a485" alpha="255" label="0.175294"/>
          <item value="0.176470588235294" color="#20a585" alpha="255" label="0.176471"/>
          <item value="0.177647058823529" color="#21a685" alpha="255" label="0.177647"/>
          <item value="0.178823529411765" color="#21a784" alpha="255" label="0.178824"/>
          <item value="0.18" color="#22a784" alpha="255" label="0.18"/>
          <item value="0.181176470588235" color="#23a883" alpha="255" label="0.181176"/>
          <item value="0.182352941176471" color="#23a982" alpha="255" label="0.182353"/>
          <item value="0.183529411764706" color="#24aa82" alpha="255" label="0.183529"/>
          <item value="0.184705882352941" color="#25ab81" alpha="255" label="0.184706"/>
          <item value="0.185882352941176" color="#26ac81" alpha="255" label="0.185882"/>
          <item value="0.187058823529412" color="#27ad80" alpha="255" label="0.187059"/>
          <item value="0.188235294117647" color="#28ae7f" alpha="255" label="0.188235"/>
          <item value="0.189411764705882" color="#29af7f" alpha="255" label="0.189412"/>
          <item value="0.190588235294118" color="#2ab07e" alpha="255" label="0.190588"/>
          <item value="0.191764705882353" color="#2bb17d" alpha="255" label="0.191765"/>
          <item value="0.192941176470588" color="#2cb17d" alpha="255" label="0.192941"/>
          <item value="0.194117647058824" color="#2eb27c" alpha="255" label="0.194118"/>
          <item value="0.195294117647059" color="#2fb37b" alpha="255" label="0.195294"/>
          <item value="0.196470588235294" color="#30b47a" alpha="255" label="0.196471"/>
          <item value="0.197647058823529" color="#32b57a" alpha="255" label="0.197647"/>
          <item value="0.198823529411765" color="#33b679" alpha="255" label="0.198824"/>
          <item value="0.2" color="#35b778" alpha="255" label="0.2"/>
          <item value="0.201176470588235" color="#36b877" alpha="255" label="0.201176"/>
          <item value="0.202352941176471" color="#38b976" alpha="255" label="0.202353"/>
          <item value="0.203529411764706" color="#39b976" alpha="255" label="0.203529"/>
          <item value="0.204705882352941" color="#3bba75" alpha="255" label="0.204706"/>
          <item value="0.205882352941176" color="#3dbb74" alpha="255" label="0.205882"/>
          <item value="0.207058823529412" color="#3ebc73" alpha="255" label="0.207059"/>
          <item value="0.208235294117647" color="#40bd72" alpha="255" label="0.208235"/>
          <item value="0.209411764705882" color="#42be71" alpha="255" label="0.209412"/>
          <item value="0.210588235294118" color="#44be70" alpha="255" label="0.210588"/>
          <item value="0.211764705882353" color="#45bf6f" alpha="255" label="0.211765"/>
          <item value="0.212941176470588" color="#47c06e" alpha="255" label="0.212941"/>
          <item value="0.214117647058824" color="#49c16d" alpha="255" label="0.214118"/>
          <item value="0.215294117647059" color="#4bc26c" alpha="255" label="0.215294"/>
          <item value="0.216470588235294" color="#4dc26b" alpha="255" label="0.216471"/>
          <item value="0.217647058823529" color="#4fc369" alpha="255" label="0.217647"/>
          <item value="0.218823529411765" color="#51c468" alpha="255" label="0.218824"/>
          <item value="0.22" color="#53c567" alpha="255" label="0.22"/>
          <item value="0.221176470588235" color="#55c666" alpha="255" label="0.221176"/>
          <item value="0.222352941176471" color="#57c665" alpha="255" label="0.222353"/>
          <item value="0.223529411764706" color="#59c764" alpha="255" label="0.223529"/>
          <item value="0.224705882352941" color="#5bc862" alpha="255" label="0.224706"/>
          <item value="0.225882352941176" color="#5ec961" alpha="255" label="0.225882"/>
          <item value="0.227058823529412" color="#60c960" alpha="255" label="0.227059"/>
          <item value="0.228235294117647" color="#62ca5f" alpha="255" label="0.228235"/>
          <item value="0.229411764705882" color="#64cb5d" alpha="255" label="0.229412"/>
          <item value="0.230588235294118" color="#67cc5c" alpha="255" label="0.230588"/>
          <item value="0.231764705882353" color="#69cc5b" alpha="255" label="0.231765"/>
          <item value="0.232941176470588" color="#6bcd59" alpha="255" label="0.232941"/>
          <item value="0.234117647058824" color="#6dce58" alpha="255" label="0.234118"/>
          <item value="0.235294117647059" color="#70ce56" alpha="255" label="0.235294"/>
          <item value="0.236470588235294" color="#72cf55" alpha="255" label="0.236471"/>
          <item value="0.237647058823529" color="#74d054" alpha="255" label="0.237647"/>
          <item value="0.238823529411765" color="#77d052" alpha="255" label="0.238824"/>
          <item value="0.24" color="#79d151" alpha="255" label="0.24"/>
          <item value="0.241176470588235" color="#7cd24f" alpha="255" label="0.241176"/>
          <item value="0.242352941176471" color="#7ed24e" alpha="255" label="0.242353"/>
          <item value="0.243529411764706" color="#81d34c" alpha="255" label="0.243529"/>
          <item value="0.244705882352941" color="#83d34b" alpha="255" label="0.244706"/>
          <item value="0.245882352941176" color="#86d449" alpha="255" label="0.245882"/>
          <item value="0.247058823529412" color="#88d547" alpha="255" label="0.247059"/>
          <item value="0.248235294117647" color="#8bd546" alpha="255" label="0.248235"/>
          <item value="0.249411764705882" color="#8dd644" alpha="255" label="0.249412"/>
          <item value="0.250588235294118" color="#90d643" alpha="255" label="0.250588"/>
          <item value="0.251764705882353" color="#92d741" alpha="255" label="0.251765"/>
          <item value="0.252941176470588" color="#95d73f" alpha="255" label="0.252941"/>
          <item value="0.254117647058824" color="#97d83e" alpha="255" label="0.254118"/>
          <item value="0.255294117647059" color="#9ad83c" alpha="255" label="0.255294"/>
          <item value="0.256470588235294" color="#9dd93a" alpha="255" label="0.256471"/>
          <item value="0.257647058823529" color="#9fd938" alpha="255" label="0.257647"/>
          <item value="0.258823529411765" color="#a2da37" alpha="255" label="0.258824"/>
          <item value="0.26" color="#a5da35" alpha="255" label="0.26"/>
          <item value="0.261176470588235" color="#a7db33" alpha="255" label="0.261176"/>
          <item value="0.262352941176471" color="#aadb32" alpha="255" label="0.262353"/>
          <item value="0.263529411764706" color="#addc30" alpha="255" label="0.263529"/>
          <item value="0.264705882352941" color="#afdc2e" alpha="255" label="0.264706"/>
          <item value="0.265882352941176" color="#b2dd2c" alpha="255" label="0.265882"/>
          <item value="0.267058823529412" color="#b5dd2b" alpha="255" label="0.267059"/>
          <item value="0.268235294117647" color="#b7dd29" alpha="255" label="0.268235"/>
          <item value="0.269411764705882" color="#bade27" alpha="255" label="0.269412"/>
          <item value="0.270588235294118" color="#bdde26" alpha="255" label="0.270588"/>
          <item value="0.271764705882353" color="#bfdf24" alpha="255" label="0.271765"/>
          <item value="0.272941176470588" color="#c2df22" alpha="255" label="0.272941"/>
          <item value="0.274117647058824" color="#c5df21" alpha="255" label="0.274118"/>
          <item value="0.275294117647059" color="#c7e01f" alpha="255" label="0.275294"/>
          <item value="0.276470588235294" color="#cae01e" alpha="255" label="0.276471"/>
          <item value="0.277647058823529" color="#cde01d" alpha="255" label="0.277647"/>
          <item value="0.278823529411765" color="#cfe11c" alpha="255" label="0.278824"/>
          <item value="0.28" color="#d2e11b" alpha="255" label="0.28"/>
          <item value="0.281176470588235" color="#d4e11a" alpha="255" label="0.281176"/>
          <item value="0.282352941176471" color="#d7e219" alpha="255" label="0.282353"/>
          <item value="0.283529411764706" color="#dae218" alpha="255" label="0.283529"/>
          <item value="0.284705882352941" color="#dce218" alpha="255" label="0.284706"/>
          <item value="0.285882352941176" color="#dfe318" alpha="255" label="0.285882"/>
          <item value="0.287058823529412" color="#e1e318" alpha="255" label="0.287059"/>
          <item value="0.288235294117647" color="#e4e318" alpha="255" label="0.288235"/>
          <item value="0.289411764705882" color="#e7e419" alpha="255" label="0.289412"/>
          <item value="0.290588235294118" color="#e9e419" alpha="255" label="0.290588"/>
          <item value="0.291764705882353" color="#ece41a" alpha="255" label="0.291765"/>
          <item value="0.292941176470588" color="#eee51b" alpha="255" label="0.292941"/>
          <item value="0.294117647058824" color="#f1e51c" alpha="255" label="0.294118"/>
          <item value="0.295294117647059" color="#f3e51e" alpha="255" label="0.295294"/>
          <item value="0.296470588235294" color="#f6e61f" alpha="255" label="0.296471"/>
          <item value="0.297647058823529" color="#f8e621" alpha="255" label="0.297647"/>
          <item value="0.298823529411765" color="#fae622" alpha="255" label="0.298824"/>
          <item value="0.3" color="#fde724" alpha="255" label="0.3"/>
          <rampLegendSettings maximumLabel="" useContinuousLegend="1" direction="0" minimumLabel="" suffix="" prefix="" orientation="2">
            <numericFormat id="basic">
              <Option type="Map">
                <Option type="invalid" name="decimal_separator"/>
                <Option value="6" type="int" name="decimals"/>
                <Option value="0" type="int" name="rounding_type"/>
                <Option value="false" type="bool" name="show_plus"/>
                <Option value="true" type="bool" name="show_thousand_separator"/>
                <Option value="false" type="bool" name="show_trailing_zeros"/>
                <Option type="invalid" name="thousand_separator"/>
              </Option>
            </numericFormat>
          </rampLegendSettings>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast contrast="0" brightness="0" gamma="1"/>
    <huesaturation colorizeGreen="128" invertColors="0" colorizeStrength="100" grayscaleMode="0" colorizeBlue="128" saturation="0" colorizeRed="255" colorizeOn="0"/>
    <rasterresampler maxOversampling="2"/>
    <resamplingStage>resamplingFilter</resamplingStage>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
