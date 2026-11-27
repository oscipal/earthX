<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.4-Prizren" styleCategories="Symbology">
  <pipe-data-defined-properties>
    <Option type="Map">
      <Option type="QString" value="" name="name"/>
      <Option name="properties"/>
      <Option type="QString" value="collection" name="type"/>
    </Option>
  </pipe-data-defined-properties>
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2" zoomedInResamplingMethod="nearestNeighbour" zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer nodataColor="" classificationMax="30" band="2" classificationMin="-20" type="singlebandpseudocolor" opacity="1" alphaBand="-1">
      <minMaxOrigin>
        <limits>None</limits>
        <extent>WholeRaster</extent>
        <statAccuracy>Estimated</statAccuracy>
        <cumulativeCutLower>0.02</cumulativeCutLower>
        <cumulativeCutUpper>0.98</cumulativeCutUpper>
        <stdDevFactor>2</stdDevFactor>
      </minMaxOrigin>
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" maximumValue="30" labelPrecision="6" clip="0" minimumValue="-20" classificationMode="1">
          <colorramp type="gradient" name="[source]">
            <Option type="Map">
              <Option type="QString" value="5,48,97,255" name="color1"/>
              <Option type="QString" value="103,0,31,255" name="color2"/>
              <Option type="QString" value="ccw" name="direction"/>
              <Option type="QString" value="0" name="discrete"/>
              <Option type="QString" value="gradient" name="rampType"/>
              <Option type="QString" value="rgb" name="spec"/>
              <Option type="QString" value="0.00392157;6,50,99,255;rgb;ccw:0.00784314;7,52,102,255;rgb;ccw:0.0117647;8,54,105,255;rgb;ccw:0.0156863;9,56,108,255;rgb;ccw:0.0196078;10,58,111,255;rgb;ccw:0.0235294;11,60,114,255;rgb;ccw:0.027451;12,62,117,255;rgb;ccw:0.0313725;13,64,120,255;rgb;ccw:0.0352941;14,67,123,255;rgb;ccw:0.0392157;15,69,126,255;rgb;ccw:0.0431373;17,71,129,255;rgb;ccw:0.0470588;18,73,132,255;rgb;ccw:0.0509804;19,75,135,255;rgb;ccw:0.054902;20,77,138,255;rgb;ccw:0.0588235;21,79,141,255;rgb;ccw:0.0627451;22,81,144,255;rgb;ccw:0.0666667;23,84,147,255;rgb;ccw:0.0705882;24,86,149,255;rgb;ccw:0.0745098;25,88,152,255;rgb;ccw:0.0784314;26,90,155,255;rgb;ccw:0.0823529;28,92,158,255;rgb;ccw:0.0862745;29,94,161,255;rgb;ccw:0.0901961;30,96,164,255;rgb;ccw:0.0941176;31,98,167,255;rgb;ccw:0.0980392;32,100,170,255;rgb;ccw:0.101961;33,102,172,255;rgb;ccw:0.105882;35,104,173,255;rgb;ccw:0.109804;36,106,174,255;rgb;ccw:0.113725;37,108,175,255;rgb;ccw:0.117647;39,109,176,255;rgb;ccw:0.121569;40,111,176,255;rgb;ccw:0.12549;41,113,177,255;rgb;ccw:0.129412;43,115,178,255;rgb;ccw:0.133333;44,117,179,255;rgb;ccw:0.137255;45,118,180,255;rgb;ccw:0.141176;47,120,181,255;rgb;ccw:0.145098;48,122,182,255;rgb;ccw:0.14902;49,124,183,255;rgb;ccw:0.152941;51,125,184,255;rgb;ccw:0.156863;52,127,185,255;rgb;ccw:0.160784;53,129,185,255;rgb;ccw:0.164706;55,131,186,255;rgb;ccw:0.168627;56,132,187,255;rgb;ccw:0.172549;57,134,188,255;rgb;ccw:0.176471;59,136,189,255;rgb;ccw:0.180392;60,138,190,255;rgb;ccw:0.184314;61,139,191,255;rgb;ccw:0.188235;63,141,192,255;rgb;ccw:0.192157;64,143,193,255;rgb;ccw:0.196078;65,145,194,255;rgb;ccw:0.2;67,147,195,255;rgb;ccw:0.203922;70,148,196,255;rgb;ccw:0.207843;73,150,197,255;rgb;ccw:0.211765;76,152,198,255;rgb;ccw:0.215686;79,154,199,255;rgb;ccw:0.219608;82,156,200,255;rgb;ccw:0.223529;85,158,201,255;rgb;ccw:0.227451;88,160,202,255;rgb;ccw:0.231373;91,162,203,255;rgb;ccw:0.235294;94,164,204,255;rgb;ccw:0.239216;97,166,205,255;rgb;ccw:0.243137;101,168,206,255;rgb;ccw:0.247059;104,170,207,255;rgb;ccw:0.25098;107,172,208,255;rgb;ccw:0.254902;110,174,209,255;rgb;ccw:0.258824;113,176,210,255;rgb;ccw:0.262745;116,178,211,255;rgb;ccw:0.266667;119,180,213,255;rgb;ccw:0.270588;122,182,214,255;rgb;ccw:0.27451;125,184,215,255;rgb;ccw:0.278431;128,186,216,255;rgb;ccw:0.282353;132,188,217,255;rgb;ccw:0.286275;135,190,218,255;rgb;ccw:0.290196;138,192,219,255;rgb;ccw:0.294118;141,194,220,255;rgb;ccw:0.298039;144,196,221,255;rgb;ccw:0.301961;147,197,222,255;rgb;ccw:0.305882;149,198,223,255;rgb;ccw:0.309804;152,200,223,255;rgb;ccw:0.313725;154,201,224,255;rgb;ccw:0.317647;157,202,225,255;rgb;ccw:0.321569;159,203,225,255;rgb;ccw:0.32549;162,205,226,255;rgb;ccw:0.329412;164,206,227,255;rgb;ccw:0.333333;167,207,228,255;rgb;ccw:0.337255;169,208,228,255;rgb;ccw:0.341176;171,210,229,255;rgb;ccw:0.345098;174,211,230,255;rgb;ccw:0.34902;176,212,230,255;rgb;ccw:0.352941;179,213,231,255;rgb;ccw:0.356863;181,215,232,255;rgb;ccw:0.360784;184,216,232,255;rgb;ccw:0.364706;186,217,233,255;rgb;ccw:0.368627;189,218,234,255;rgb;ccw:0.372549;191,220,235,255;rgb;ccw:0.376471;194,221,235,255;rgb;ccw:0.380392;196,222,236,255;rgb;ccw:0.384314;199,223,237,255;rgb;ccw:0.388235;201,225,237,255;rgb;ccw:0.392157;204,226,238,255;rgb;ccw:0.396078;206,227,239,255;rgb;ccw:0.4;209,229,240,255;rgb;ccw:0.403922;210,229,240,255;rgb;ccw:0.407843;211,230,240,255;rgb;ccw:0.411765;213,231,240,255;rgb;ccw:0.415686;214,231,241,255;rgb;ccw:0.419608;216,232,241,255;rgb;ccw:0.423529;217,233,241,255;rgb;ccw:0.427451;219,233,241,255;rgb;ccw:0.431373;220,234,242,255;rgb;ccw:0.435294;222,235,242,255;rgb;ccw:0.439216;223,236,242,255;rgb;ccw:0.443137;225,236,243,255;rgb;ccw:0.447059;226,237,243,255;rgb;ccw:0.45098;228,238,243,255;rgb;ccw:0.454902;229,238,243,255;rgb;ccw:0.458824;231,239,244,255;rgb;ccw:0.462745;232,240,244,255;rgb;ccw:0.466667;234,241,244,255;rgb;ccw:0.470588;235,241,244,255;rgb;ccw:0.47451;237,242,245,255;rgb;ccw:0.478431;238,243,245,255;rgb;ccw:0.482353;240,243,245,255;rgb;ccw:0.486275;241,244,246,255;rgb;ccw:0.490196;243,245,246,255;rgb;ccw:0.494118;244,245,246,255;rgb;ccw:0.498039;246,246,246,255;rgb;ccw:0.501961;247,246,246,255;rgb;ccw:0.505882;247,245,244,255;rgb;ccw:0.509804;247,244,242,255;rgb;ccw:0.513725;247,243,240,255;rgb;ccw:0.517647;248,242,238,255;rgb;ccw:0.521569;248,240,236,255;rgb;ccw:0.52549;248,239,234,255;rgb;ccw:0.529412;248,238,232,255;rgb;ccw:0.533333;249,237,231,255;rgb;ccw:0.537255;249,236,229,255;rgb;ccw:0.541176;249,235,227,255;rgb;ccw:0.545098;249,234,225,255;rgb;ccw:0.54902;249,233,223,255;rgb;ccw:0.552941;250,232,221,255;rgb;ccw:0.556863;250,231,219,255;rgb;ccw:0.560784;250,229,217,255;rgb;ccw:0.564706;250,228,215,255;rgb;ccw:0.568627;251,227,214,255;rgb;ccw:0.572549;251,226,212,255;rgb;ccw:0.576471;251,225,210,255;rgb;ccw:0.580392;251,224,208,255;rgb;ccw:0.584314;252,223,206,255;rgb;ccw:0.588235;252,222,204,255;rgb;ccw:0.592157;252,221,202,255;rgb;ccw:0.596078;252,220,200,255;rgb;ccw:0.6;253,219,199,255;rgb;ccw:0.603922;252,216,196,255;rgb;ccw:0.607843;252,214,193,255;rgb;ccw:0.611765;251,212,190,255;rgb;ccw:0.615686;251,210,188,255;rgb;ccw:0.619608;251,208,185,255;rgb;ccw:0.623529;250,206,182,255;rgb;ccw:0.627451;250,204,180,255;rgb;ccw:0.631373;250,202,177,255;rgb;ccw:0.635294;249,199,174,255;rgb;ccw:0.639216;249,197,171,255;rgb;ccw:0.643137;249,195,169,255;rgb;ccw:0.647059;248,193,166,255;rgb;ccw:0.65098;248,191,163,255;rgb;ccw:0.654902;248,189,161,255;rgb;ccw:0.658824;247,187,158,255;rgb;ccw:0.662745;247,185,155,255;rgb;ccw:0.666667;247,183,153,255;rgb;ccw:0.670588;246,180,150,255;rgb;ccw:0.67451;246,178,147,255;rgb;ccw:0.678431;245,176,144,255;rgb;ccw:0.682353;245,174,142,255;rgb;ccw:0.686275;245,172,139,255;rgb;ccw:0.690196;244,170,136,255;rgb;ccw:0.694118;244,168,134,255;rgb;ccw:0.698039;244,166,131,255;rgb;ccw:0.701961;243,163,128,255;rgb;ccw:0.705882;242,160,126,255;rgb;ccw:0.709804;241,158,124,255;rgb;ccw:0.713725;239,155,122,255;rgb;ccw:0.717647;238,152,120,255;rgb;ccw:0.721569;237,150,118,255;rgb;ccw:0.72549;236,147,116,255;rgb;ccw:0.729412;235,144,114,255;rgb;ccw:0.733333;234,142,112,255;rgb;ccw:0.737255;232,139,110,255;rgb;ccw:0.741176;231,136,108,255;rgb;ccw:0.745098;230,133,106,255;rgb;ccw:0.74902;229,131,104,255;rgb;ccw:0.752941;228,128,101,255;rgb;ccw:0.756863;226,125,99,255;rgb;ccw:0.760784;225,123,97,255;rgb;ccw:0.764706;224,120,95,255;rgb;ccw:0.768627;223,117,93,255;rgb;ccw:0.772549;222,114,91,255;rgb;ccw:0.776471;221,112,89,255;rgb;ccw:0.780392;219,109,87,255;rgb;ccw:0.784314;218,106,85,255;rgb;ccw:0.788235;217,104,83,255;rgb;ccw:0.792157;216,101,81,255;rgb;ccw:0.796078;215,98,79,255;rgb;ccw:0.8;214,96,77,255;rgb;ccw:0.803922;212,93,75,255;rgb;ccw:0.807843;211,90,74,255;rgb;ccw:0.811765;209,87,73,255;rgb;ccw:0.815686;208,84,71,255;rgb;ccw:0.819608;206,81,70,255;rgb;ccw:0.823529;205,79,69,255;rgb;ccw:0.827451;204,76,67,255;rgb;ccw:0.831373;202,73,66,255;rgb;ccw:0.835294;201,70,65,255;rgb;ccw:0.839216;199,67,63,255;rgb;ccw:0.843137;198,64,62,255;rgb;ccw:0.847059;197,62,60,255;rgb;ccw:0.85098;195,59,59,255;rgb;ccw:0.854902;194,56,58,255;rgb;ccw:0.858824;192,53,56,255;rgb;ccw:0.862745;191,50,55,255;rgb;ccw:0.866667;190,48,54,255;rgb;ccw:0.870588;188,45,52,255;rgb;ccw:0.87451;187,42,51,255;rgb;ccw:0.878431;185,39,50,255;rgb;ccw:0.882353;184,36,49,255;rgb;ccw:0.886275;182,33,47,255;rgb;ccw:0.890196;181,31,46,255;rgb;ccw:0.894118;180,28,45,255;rgb;ccw:0.898039;178,25,43,255;rgb;ccw:0.901961;176,23,42,255;rgb;ccw:0.905882;173,22,42,255;rgb;ccw:0.909804;170,21,41,255;rgb;ccw:0.913725;167,20,41,255;rgb;ccw:0.917647;164,19,40,255;rgb;ccw:0.921569;161,18,40,255;rgb;ccw:0.92549;158,17,39,255;rgb;ccw:0.929412;155,16,39,255;rgb;ccw:0.933333;153,16,39,255;rgb;ccw:0.937255;150,15,38,255;rgb;ccw:0.941176;147,14,38,255;rgb;ccw:0.945098;144,13,37,255;rgb;ccw:0.94902;141,12,37,255;rgb;ccw:0.952941;138,11,36,255;rgb;ccw:0.956863;135,10,36,255;rgb;ccw:0.960784;132,9,35,255;rgb;ccw:0.964706;129,8,35,255;rgb;ccw:0.968627;126,7,34,255;rgb;ccw:0.972549;123,6,34,255;rgb;ccw:0.976471;120,5,33,255;rgb;ccw:0.980392;117,4,33,255;rgb;ccw:0.984314;114,3,32,255;rgb;ccw:0.988235;111,2,32,255;rgb;ccw:0.992157;108,1,31,255;rgb;ccw:0.996078;105,0,31,255;rgb;ccw" name="stops"/>
            </Option>
          </colorramp>
          <item label="-20" alpha="255" color="#053061" value="-20"/>
          <item label="-19.8039" alpha="255" color="#063263" value="-19.80392156862745"/>
          <item label="-19.6078" alpha="255" color="#073466" value="-19.607843137254903"/>
          <item label="-19.4118" alpha="255" color="#083669" value="-19.41176470588235"/>
          <item label="-19.2157" alpha="255" color="#09386c" value="-19.215686274509803"/>
          <item label="-19.0196" alpha="255" color="#0a3a6f" value="-19.019607843137255"/>
          <item label="-18.8235" alpha="255" color="#0b3c72" value="-18.823529411764707"/>
          <item label="-18.6275" alpha="255" color="#0c3e75" value="-18.627450980392158"/>
          <item label="-18.4314" alpha="255" color="#0d4078" value="-18.431372549019606"/>
          <item label="-18.2353" alpha="255" color="#0e437b" value="-18.235294117647058"/>
          <item label="-18.0392" alpha="255" color="#0f457e" value="-18.03921568627451"/>
          <item label="-17.8431" alpha="255" color="#114781" value="-17.84313725490196"/>
          <item label="-17.6471" alpha="255" color="#124984" value="-17.647058823529413"/>
          <item label="-17.451" alpha="255" color="#134b87" value="-17.450980392156865"/>
          <item label="-17.2549" alpha="255" color="#144d8a" value="-17.254901960784313"/>
          <item label="-17.0588" alpha="255" color="#154f8d" value="-17.058823529411764"/>
          <item label="-16.8627" alpha="255" color="#165190" value="-16.862745098039216"/>
          <item label="-16.6667" alpha="255" color="#175493" value="-16.666666666666668"/>
          <item label="-16.4706" alpha="255" color="#185695" value="-16.470588235294116"/>
          <item label="-16.2745" alpha="255" color="#195898" value="-16.274509803921568"/>
          <item label="-16.0784" alpha="255" color="#1a5a9b" value="-16.07843137254902"/>
          <item label="-15.8824" alpha="255" color="#1c5c9e" value="-15.882352941176471"/>
          <item label="-15.6863" alpha="255" color="#1d5ea1" value="-15.686274509803923"/>
          <item label="-15.4902" alpha="255" color="#1e60a4" value="-15.490196078431373"/>
          <item label="-15.2941" alpha="255" color="#1f62a7" value="-15.294117647058822"/>
          <item label="-15.098" alpha="255" color="#2064aa" value="-15.098039215686274"/>
          <item label="-14.902" alpha="255" color="#2166ac" value="-14.901960784313726"/>
          <item label="-14.7059" alpha="255" color="#2368ad" value="-14.705882352941178"/>
          <item label="-14.5098" alpha="255" color="#246aae" value="-14.509803921568627"/>
          <item label="-14.3137" alpha="255" color="#256caf" value="-14.313725490196077"/>
          <item label="-14.1176" alpha="255" color="#276db0" value="-14.117647058823529"/>
          <item label="-13.9216" alpha="255" color="#286fb0" value="-13.92156862745098"/>
          <item label="-13.7255" alpha="255" color="#2971b1" value="-13.725490196078432"/>
          <item label="-13.5294" alpha="255" color="#2b73b2" value="-13.529411764705882"/>
          <item label="-13.3333" alpha="255" color="#2c75b3" value="-13.333333333333332"/>
          <item label="-13.1373" alpha="255" color="#2d76b4" value="-13.137254901960784"/>
          <item label="-12.9412" alpha="255" color="#2f78b5" value="-12.941176470588236"/>
          <item label="-12.7451" alpha="255" color="#307ab6" value="-12.745098039215687"/>
          <item label="-12.549" alpha="255" color="#317cb7" value="-12.549019607843137"/>
          <item label="-12.3529" alpha="255" color="#337db8" value="-12.352941176470587"/>
          <item label="-12.1569" alpha="255" color="#347fb9" value="-12.156862745098039"/>
          <item label="-11.9608" alpha="255" color="#3581b9" value="-11.96078431372549"/>
          <item label="-11.7647" alpha="255" color="#3783ba" value="-11.764705882352942"/>
          <item label="-11.5686" alpha="255" color="#3884bb" value="-11.568627450980392"/>
          <item label="-11.3725" alpha="255" color="#3986bc" value="-11.372549019607844"/>
          <item label="-11.1765" alpha="255" color="#3b88bd" value="-11.176470588235293"/>
          <item label="-10.9804" alpha="255" color="#3c8abe" value="-10.980392156862745"/>
          <item label="-10.7843" alpha="255" color="#3d8bbf" value="-10.784313725490197"/>
          <item label="-10.5882" alpha="255" color="#3f8dc0" value="-10.588235294117647"/>
          <item label="-10.3922" alpha="255" color="#408fc1" value="-10.392156862745098"/>
          <item label="-10.1961" alpha="255" color="#4191c2" value="-10.196078431372548"/>
          <item label="-10" alpha="255" color="#4393c3" value="-10"/>
          <item label="-9.80392" alpha="255" color="#4694c4" value="-9.803921568627452"/>
          <item label="-9.60784" alpha="255" color="#4996c5" value="-9.607843137254902"/>
          <item label="-9.41176" alpha="255" color="#4c98c6" value="-9.411764705882353"/>
          <item label="-9.21569" alpha="255" color="#4f9ac7" value="-9.215686274509803"/>
          <item label="-9.01961" alpha="255" color="#529cc8" value="-9.019607843137255"/>
          <item label="-8.82353" alpha="255" color="#559ec9" value="-8.823529411764707"/>
          <item label="-8.62745" alpha="255" color="#58a0ca" value="-8.627450980392156"/>
          <item label="-8.43137" alpha="255" color="#5ba2cb" value="-8.431372549019608"/>
          <item label="-8.23529" alpha="255" color="#5ea4cc" value="-8.235294117647058"/>
          <item label="-8.03922" alpha="255" color="#61a6cd" value="-8.03921568627451"/>
          <item label="-7.84314" alpha="255" color="#65a8ce" value="-7.843137254901961"/>
          <item label="-7.64706" alpha="255" color="#68aacf" value="-7.64705882352941"/>
          <item label="-7.45098" alpha="255" color="#6bacd0" value="-7.450980392156863"/>
          <item label="-7.2549" alpha="255" color="#6eaed1" value="-7.254901960784315"/>
          <item label="-7.05882" alpha="255" color="#71b0d2" value="-7.058823529411764"/>
          <item label="-6.86275" alpha="255" color="#74b2d3" value="-6.862745098039216"/>
          <item label="-6.66667" alpha="255" color="#77b4d5" value="-6.666666666666666"/>
          <item label="-6.47059" alpha="255" color="#7ab6d6" value="-6.470588235294118"/>
          <item label="-6.27451" alpha="255" color="#7db8d7" value="-6.27450980392157"/>
          <item label="-6.07843" alpha="255" color="#80bad8" value="-6.07843137254902"/>
          <item label="-5.88235" alpha="255" color="#84bcd9" value="-5.88235294117647"/>
          <item label="-5.68627" alpha="255" color="#87beda" value="-5.68627450980392"/>
          <item label="-5.4902" alpha="255" color="#8ac0db" value="-5.490196078431373"/>
          <item label="-5.29412" alpha="255" color="#8dc2dc" value="-5.294117647058824"/>
          <item label="-5.09804" alpha="255" color="#90c4dd" value="-5.098039215686274"/>
          <item label="-4.90196" alpha="255" color="#93c5de" value="-4.901960784313726"/>
          <item label="-4.70588" alpha="255" color="#95c6df" value="-4.705882352941176"/>
          <item label="-4.5098" alpha="255" color="#98c8df" value="-4.509803921568627"/>
          <item label="-4.31373" alpha="255" color="#9ac9e0" value="-4.31372549019608"/>
          <item label="-4.11765" alpha="255" color="#9dcae1" value="-4.11764705882353"/>
          <item label="-3.92157" alpha="255" color="#9fcbe1" value="-3.92156862745098"/>
          <item label="-3.72549" alpha="255" color="#a2cde2" value="-3.725490196078432"/>
          <item label="-3.52941" alpha="255" color="#a4cee3" value="-3.529411764705884"/>
          <item label="-3.33333" alpha="255" color="#a7cfe4" value="-3.333333333333332"/>
          <item label="-3.13725" alpha="255" color="#a9d0e4" value="-3.137254901960784"/>
          <item label="-2.94118" alpha="255" color="#abd2e5" value="-2.941176470588236"/>
          <item label="-2.7451" alpha="255" color="#aed3e6" value="-2.745098039215687"/>
          <item label="-2.54902" alpha="255" color="#b0d4e6" value="-2.549019607843139"/>
          <item label="-2.35294" alpha="255" color="#b3d5e7" value="-2.352941176470587"/>
          <item label="-2.15686" alpha="255" color="#b5d7e8" value="-2.156862745098039"/>
          <item label="-1.96078" alpha="255" color="#b8d8e8" value="-1.96078431372549"/>
          <item label="-1.76471" alpha="255" color="#bad9e9" value="-1.764705882352942"/>
          <item label="-1.56863" alpha="255" color="#bddaea" value="-1.568627450980394"/>
          <item label="-1.37255" alpha="255" color="#bfdceb" value="-1.372549019607842"/>
          <item label="-1.17647" alpha="255" color="#c2ddeb" value="-1.176470588235293"/>
          <item label="-0.980392" alpha="255" color="#c4deec" value="-0.980392156862745"/>
          <item label="-0.784314" alpha="255" color="#c7dfed" value="-0.784313725490197"/>
          <item label="-0.588235" alpha="255" color="#c9e1ed" value="-0.588235294117649"/>
          <item label="-0.392157" alpha="255" color="#cce2ee" value="-0.392156862745097"/>
          <item label="-0.196078" alpha="255" color="#cee3ef" value="-0.196078431372548"/>
          <item label="0" alpha="255" color="#d1e5f0" value="0"/>
          <item label="0.196078" alpha="255" color="#d2e5f0" value="0.196078431372548"/>
          <item label="0.392157" alpha="255" color="#d3e6f0" value="0.392156862745097"/>
          <item label="0.588235" alpha="255" color="#d5e7f0" value="0.588235294117649"/>
          <item label="0.784314" alpha="255" color="#d6e7f1" value="0.784313725490197"/>
          <item label="0.980392" alpha="255" color="#d8e8f1" value="0.980392156862745"/>
          <item label="1.17647" alpha="255" color="#d9e9f1" value="1.176470588235293"/>
          <item label="1.37255" alpha="255" color="#dbe9f1" value="1.372549019607842"/>
          <item label="1.56863" alpha="255" color="#dceaf2" value="1.568627450980394"/>
          <item label="1.76471" alpha="255" color="#deebf2" value="1.764705882352942"/>
          <item label="1.96078" alpha="255" color="#dfecf2" value="1.96078431372549"/>
          <item label="2.15686" alpha="255" color="#e1ecf3" value="2.156862745098039"/>
          <item label="2.35294" alpha="255" color="#e2edf3" value="2.352941176470587"/>
          <item label="2.54902" alpha="255" color="#e4eef3" value="2.549019607843139"/>
          <item label="2.7451" alpha="255" color="#e5eef3" value="2.745098039215687"/>
          <item label="2.94118" alpha="255" color="#e7eff4" value="2.941176470588236"/>
          <item label="3.13725" alpha="255" color="#e8f0f4" value="3.137254901960784"/>
          <item label="3.33333" alpha="255" color="#eaf1f4" value="3.333333333333332"/>
          <item label="3.52941" alpha="255" color="#ebf1f4" value="3.529411764705884"/>
          <item label="3.72549" alpha="255" color="#edf2f5" value="3.725490196078432"/>
          <item label="3.92157" alpha="255" color="#eef3f5" value="3.92156862745098"/>
          <item label="4.11765" alpha="255" color="#f0f3f5" value="4.11764705882353"/>
          <item label="4.31373" alpha="255" color="#f1f4f6" value="4.313725490196077"/>
          <item label="4.5098" alpha="255" color="#f3f5f6" value="4.50980392156863"/>
          <item label="4.70588" alpha="255" color="#f4f5f6" value="4.705882352941178"/>
          <item label="4.90196" alpha="255" color="#f6f6f6" value="4.901960784313726"/>
          <item label="5.09804" alpha="255" color="#f7f6f6" value="5.098039215686274"/>
          <item label="5.29412" alpha="255" color="#f7f5f4" value="5.294117647058822"/>
          <item label="5.4902" alpha="255" color="#f7f4f2" value="5.49019607843137"/>
          <item label="5.68627" alpha="255" color="#f7f3f0" value="5.686274509803923"/>
          <item label="5.88235" alpha="255" color="#f8f2ee" value="5.88235294117647"/>
          <item label="6.07843" alpha="255" color="#f8f0ec" value="6.07843137254902"/>
          <item label="6.27451" alpha="255" color="#f8efea" value="6.274509803921568"/>
          <item label="6.47059" alpha="255" color="#f8eee8" value="6.470588235294116"/>
          <item label="6.66667" alpha="255" color="#f9ede7" value="6.666666666666668"/>
          <item label="6.86275" alpha="255" color="#f9ece5" value="6.862745098039216"/>
          <item label="7.05882" alpha="255" color="#f9ebe3" value="7.058823529411764"/>
          <item label="7.2549" alpha="255" color="#f9eae1" value="7.254901960784313"/>
          <item label="7.45098" alpha="255" color="#f9e9df" value="7.45098039215686"/>
          <item label="7.64706" alpha="255" color="#fae8dd" value="7.647058823529413"/>
          <item label="7.84314" alpha="255" color="#fae7db" value="7.843137254901961"/>
          <item label="8.03922" alpha="255" color="#fae5d9" value="8.03921568627451"/>
          <item label="8.23529" alpha="255" color="#fae4d7" value="8.235294117647058"/>
          <item label="8.43137" alpha="255" color="#fbe3d6" value="8.431372549019606"/>
          <item label="8.62745" alpha="255" color="#fbe2d4" value="8.627450980392158"/>
          <item label="8.82353" alpha="255" color="#fbe1d2" value="8.823529411764707"/>
          <item label="9.01961" alpha="255" color="#fbe0d0" value="9.019607843137255"/>
          <item label="9.21569" alpha="255" color="#fcdfce" value="9.215686274509803"/>
          <item label="9.41176" alpha="255" color="#fcdecc" value="9.411764705882351"/>
          <item label="9.60784" alpha="255" color="#fcddca" value="9.607843137254903"/>
          <item label="9.80392" alpha="255" color="#fcdcc8" value="9.803921568627452"/>
          <item label="10" alpha="255" color="#fddbc7" value="10"/>
          <item label="10.1961" alpha="255" color="#fcd8c4" value="10.196078431372548"/>
          <item label="10.3922" alpha="255" color="#fcd6c1" value="10.392156862745097"/>
          <item label="10.5882" alpha="255" color="#fbd4be" value="10.588235294117649"/>
          <item label="10.7843" alpha="255" color="#fbd2bc" value="10.784313725490197"/>
          <item label="10.9804" alpha="255" color="#fbd0b9" value="10.980392156862745"/>
          <item label="11.1765" alpha="255" color="#faceb6" value="11.176470588235293"/>
          <item label="11.3725" alpha="255" color="#faccb4" value="11.372549019607842"/>
          <item label="11.5686" alpha="255" color="#facab1" value="11.568627450980394"/>
          <item label="11.7647" alpha="255" color="#f9c7ae" value="11.764705882352942"/>
          <item label="11.9608" alpha="255" color="#f9c5ab" value="11.96078431372549"/>
          <item label="12.1569" alpha="255" color="#f9c3a9" value="12.156862745098039"/>
          <item label="12.3529" alpha="255" color="#f8c1a6" value="12.352941176470587"/>
          <item label="12.549" alpha="255" color="#f8bfa3" value="12.549019607843135"/>
          <item label="12.7451" alpha="255" color="#f8bda1" value="12.745098039215684"/>
          <item label="12.9412" alpha="255" color="#f7bb9e" value="12.941176470588232"/>
          <item label="13.1373" alpha="255" color="#f7b99b" value="13.137254901960787"/>
          <item label="13.3333" alpha="255" color="#f7b799" value="13.333333333333336"/>
          <item label="13.5294" alpha="255" color="#f6b496" value="13.529411764705884"/>
          <item label="13.7255" alpha="255" color="#f6b293" value="13.725490196078432"/>
          <item label="13.9216" alpha="255" color="#f5b090" value="13.92156862745098"/>
          <item label="14.1176" alpha="255" color="#f5ae8e" value="14.117647058823529"/>
          <item label="14.3137" alpha="255" color="#f5ac8b" value="14.313725490196077"/>
          <item label="14.5098" alpha="255" color="#f4aa88" value="14.509803921568626"/>
          <item label="14.7059" alpha="255" color="#f4a886" value="14.705882352941174"/>
          <item label="14.902" alpha="255" color="#f4a683" value="14.901960784313722"/>
          <item label="15.098" alpha="255" color="#f3a380" value="15.098039215686278"/>
          <item label="15.2941" alpha="255" color="#f2a07e" value="15.294117647058826"/>
          <item label="15.4902" alpha="255" color="#f19e7c" value="15.490196078431374"/>
          <item label="15.6863" alpha="255" color="#ef9b7a" value="15.686274509803923"/>
          <item label="15.8824" alpha="255" color="#ee9878" value="15.882352941176471"/>
          <item label="16.0784" alpha="255" color="#ed9676" value="16.07843137254902"/>
          <item label="16.2745" alpha="255" color="#ec9374" value="16.274509803921568"/>
          <item label="16.4706" alpha="255" color="#eb9072" value="16.470588235294116"/>
          <item label="16.6667" alpha="255" color="#ea8e70" value="16.666666666666664"/>
          <item label="16.8627" alpha="255" color="#e88b6e" value="16.862745098039213"/>
          <item label="17.0588" alpha="255" color="#e7886c" value="17.058823529411768"/>
          <item label="17.2549" alpha="255" color="#e6856a" value="17.254901960784316"/>
          <item label="17.451" alpha="255" color="#e58368" value="17.450980392156865"/>
          <item label="17.6471" alpha="255" color="#e48065" value="17.647058823529413"/>
          <item label="17.8431" alpha="255" color="#e27d63" value="17.84313725490196"/>
          <item label="18.0392" alpha="255" color="#e17b61" value="18.03921568627451"/>
          <item label="18.2353" alpha="255" color="#e0785f" value="18.235294117647058"/>
          <item label="18.4314" alpha="255" color="#df755d" value="18.431372549019606"/>
          <item label="18.6275" alpha="255" color="#de725b" value="18.627450980392155"/>
          <item label="18.8235" alpha="255" color="#dd7059" value="18.823529411764703"/>
          <item label="19.0196" alpha="255" color="#db6d57" value="19.01960784313726"/>
          <item label="19.2157" alpha="255" color="#da6a55" value="19.215686274509807"/>
          <item label="19.4118" alpha="255" color="#d96853" value="19.411764705882355"/>
          <item label="19.6078" alpha="255" color="#d86551" value="19.607843137254903"/>
          <item label="19.8039" alpha="255" color="#d7624f" value="19.80392156862745"/>
          <item label="20" alpha="255" color="#d6604d" value="20"/>
          <item label="20.1961" alpha="255" color="#d45d4b" value="20.19607843137255"/>
          <item label="20.3922" alpha="255" color="#d35a4a" value="20.392156862745097"/>
          <item label="20.5882" alpha="255" color="#d15749" value="20.588235294117645"/>
          <item label="20.7843" alpha="255" color="#d05447" value="20.784313725490193"/>
          <item label="20.9804" alpha="255" color="#ce5146" value="20.98039215686274"/>
          <item label="21.1765" alpha="255" color="#cd4f45" value="21.176470588235297"/>
          <item label="21.3725" alpha="255" color="#cc4c43" value="21.372549019607845"/>
          <item label="21.5686" alpha="255" color="#ca4942" value="21.568627450980394"/>
          <item label="21.7647" alpha="255" color="#c94641" value="21.764705882352942"/>
          <item label="21.9608" alpha="255" color="#c7433f" value="21.96078431372549"/>
          <item label="22.1569" alpha="255" color="#c6403e" value="22.15686274509804"/>
          <item label="22.3529" alpha="255" color="#c53e3c" value="22.352941176470587"/>
          <item label="22.549" alpha="255" color="#c33b3b" value="22.549019607843135"/>
          <item label="22.7451" alpha="255" color="#c2383a" value="22.745098039215684"/>
          <item label="22.9412" alpha="255" color="#c03538" value="22.941176470588232"/>
          <item label="23.1373" alpha="255" color="#bf3237" value="23.137254901960787"/>
          <item label="23.3333" alpha="255" color="#be3036" value="23.333333333333336"/>
          <item label="23.5294" alpha="255" color="#bc2d34" value="23.529411764705884"/>
          <item label="23.7255" alpha="255" color="#bb2a33" value="23.725490196078432"/>
          <item label="23.9216" alpha="255" color="#b92732" value="23.92156862745098"/>
          <item label="24.1176" alpha="255" color="#b82431" value="24.11764705882353"/>
          <item label="24.3137" alpha="255" color="#b6212f" value="24.313725490196077"/>
          <item label="24.5098" alpha="255" color="#b51f2e" value="24.509803921568626"/>
          <item label="24.7059" alpha="255" color="#b41c2d" value="24.705882352941174"/>
          <item label="24.902" alpha="255" color="#b2192b" value="24.901960784313722"/>
          <item label="25.098" alpha="255" color="#b0172a" value="25.098039215686278"/>
          <item label="25.2941" alpha="255" color="#ad162a" value="25.294117647058826"/>
          <item label="25.4902" alpha="255" color="#aa1529" value="25.490196078431374"/>
          <item label="25.6863" alpha="255" color="#a71429" value="25.686274509803923"/>
          <item label="25.8824" alpha="255" color="#a41328" value="25.88235294117647"/>
          <item label="26.0784" alpha="255" color="#a11228" value="26.07843137254902"/>
          <item label="26.2745" alpha="255" color="#9e1127" value="26.274509803921568"/>
          <item label="26.4706" alpha="255" color="#9b1027" value="26.470588235294116"/>
          <item label="26.6667" alpha="255" color="#991027" value="26.666666666666664"/>
          <item label="26.8627" alpha="255" color="#960f26" value="26.862745098039213"/>
          <item label="27.0588" alpha="255" color="#930e26" value="27.058823529411768"/>
          <item label="27.2549" alpha="255" color="#900d25" value="27.254901960784316"/>
          <item label="27.451" alpha="255" color="#8d0c25" value="27.450980392156865"/>
          <item label="27.6471" alpha="255" color="#8a0b24" value="27.647058823529413"/>
          <item label="27.8431" alpha="255" color="#870a24" value="27.84313725490196"/>
          <item label="28.0392" alpha="255" color="#840923" value="28.03921568627451"/>
          <item label="28.2353" alpha="255" color="#810823" value="28.235294117647058"/>
          <item label="28.4314" alpha="255" color="#7e0722" value="28.431372549019606"/>
          <item label="28.6275" alpha="255" color="#7b0622" value="28.627450980392155"/>
          <item label="28.8235" alpha="255" color="#780521" value="28.823529411764703"/>
          <item label="29.0196" alpha="255" color="#750421" value="29.01960784313726"/>
          <item label="29.2157" alpha="255" color="#720320" value="29.215686274509807"/>
          <item label="29.4118" alpha="255" color="#6f0220" value="29.411764705882355"/>
          <item label="29.6078" alpha="255" color="#6c011f" value="29.607843137254903"/>
          <item label="29.8039" alpha="255" color="#69001f" value="29.80392156862745"/>
          <item label="30" alpha="255" color="#67001f" value="30"/>
          <rampLegendSettings prefix="" useContinuousLegend="1" suffix="" orientation="2" maximumLabel="" minimumLabel="" direction="0">
            <numericFormat id="basic">
              <Option type="Map">
                <Option type="invalid" name="decimal_separator"/>
                <Option type="int" value="6" name="decimals"/>
                <Option type="int" value="0" name="rounding_type"/>
                <Option type="bool" value="false" name="show_plus"/>
                <Option type="bool" value="true" name="show_thousand_separator"/>
                <Option type="bool" value="false" name="show_trailing_zeros"/>
                <Option type="invalid" name="thousand_separator"/>
              </Option>
            </numericFormat>
          </rampLegendSettings>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast brightness="0" gamma="1" contrast="0"/>
    <huesaturation colorizeGreen="128" colorizeBlue="128" colorizeStrength="100" colorizeRed="255" grayscaleMode="0" colorizeOn="0" saturation="0" invertColors="0"/>
    <rasterresampler maxOversampling="2"/>
    <resamplingStage>resamplingFilter</resamplingStage>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
