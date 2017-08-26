<?php

$option_text = "i:";
$option_text .= "o:";
$option_text .= "u";

$option = getopt($option_text);

var_dump($option);

define('EOL',(PHP_SAPI == 'cli') ? PHP_EOL : '<br />');

require_once dirname(__FILE__) . '/phpexcel/Classes/PHPExcel/IOFactory.php';

// Check if file name is in argument
if (array_key_exists("i", $option)){
	$filename = $option["i"];
} else {
	$filename = "Stock Codes.xlsx";
}

if (array_key_exists("o", $option)){
	$config_file_name = $option["o"];
} else {
	$config_file_name = "lov.cfg";
}

if (!file_exists($filename)) 
{
	exit("File not exist." . EOL);
}

echo "File " , $filename , " exists";
echo '<hr />';

/**  Identify the type of $inputFileName  **/
$inputFileType = PHPExcel_IOFactory::identify($filename);
/**  Create a new Reader of the type that has been identified  **/
$objReader = PHPExcel_IOFactory::createReader($inputFileType);
//$objReader->setReadDataOnly(true);
/**  Load $inputFileName to a PHPExcel Object  **/
$objPHPExcel = $objReader->load($filename);

echo "File " , $filename , " loaded";
echo '<hr />';

echo 'Reading the number of Worksheets in the WorkBook<br />';
/**  Use the PHPExcel object's getSheetCount() method to get a count of the number of WorkSheets in the WorkBook  */
$sheetCount = $objPHPExcel->getSheetCount();
echo 'There ',(($sheetCount == 1) ? 'is' : 'are'),' ',$sheetCount,' WorkSheet',(($sheetCount == 1) ? '' : 's'),' in the WorkBook<br /><br />';

echo 'Reading Tool sheet and loop every target sheet to write lov.cfg <br /><br />';

$file_content = "";

/**  Use the PHPExcel object's getSheetNames() method to get an array listing the names/titles of the WorkSheets in the WorkBook  */
$sheetNames = $objPHPExcel->getSheetNames();
foreach($sheetNames as $sheetIndex => $sheetName) {
	// Read 'Tool' sheet to get setup data
	if ($sheetName == 'Tool'){
		$active = $objPHPExcel->setActiveSheetIndex($sheetIndex);	
		$range = $active->calculateWorksheetDimension();
		echo "Data range in setup table is " , $range , "<br />";
		$data = $active->rangeToArray($range, NULL, true, true);

		$index = 0;
		$map_index = 0;
		// Array containing Target sheet as Key and mapping values as Array
		$target_sheet_mapping = array();
		
		echo "<table border='1'>";
		foreach ($data as $row) {
			echo "<tr><td>" . $row[0] . "</td><td>";
			if ($index > 0){
				if (!is_null($row[1])){
					$lov_group = array();
					foreach(explode(',', $row[1]) as $group){						
						foreach (explode('=', $group) as $map) {
							if ($map_index == 0){
								$map_index = 1;
								$map_group = $map;
							} else {
								$map_index = 0;
								$map_column = $map;
							}
						}
						echo $map_group . " = " . $map_column . "<br/>";
						$lov_group[$map_group] = $map_column;
					}
					//echo "<br/>";
					$target_sheet_mapping[$row[0]] = $lov_group;
				}
			} else {
				echo $row[1];
			}
			echo "</td></tr>";
			$index++;
		}
		echo "</table>";
		echo "<br/>";

	}
	else {
		if (array_key_exists($sheetIndex, $target_sheet_mapping)){
			$active = $objPHPExcel->setActiveSheetIndex($sheetIndex);			
			foreach ($target_sheet_mapping[$sheetIndex] as $key => $value) {
				//echo $key . "and" . $value . "<br/>";
				$file_content .= '"' . $key . '"' . ':[
';
				$col = explode(":", $value);
				echo "<br / >[" . $key . "] from sheetIndex " . $sheetIndex . " Columns " . 
					 $col[0] . ":" . $col[1] . "  <br / >";
				//echo $col[0] . " and " . $col[1] . "<br/>";
				for ($row = 3; $row < $active->getHighestRow(); $row++){
					$cell1 = $active->getCell($col[0].$row);
					$cell2 = $active->getCell($col[1].$row);
					echo $cell1 . " : " . $cell2;
					if ($cell1 == "…"){
						echo '***Break***<br/>';						
						break;
					} elseif ($cell1->getCalculatedValue() == NULL or 
							$cell1->getCalculatedValue() == ''){
						echo '***Skip***<br/>';
						continue;
					} else {
						echo "<br/>";
						
						$file_content .= '	{' . '
		code: "' . $cell1->getCalculatedValue() . '"
';
						if ($cell2->getCalculatedValue() != NULL or $cell2->getCalculatedValue() != ''){
							$file_content .= '		label: "' . $cell2->getCalculatedValue() . '"';
						}
						$file_content .= '
	}
';
						
					}
				}
				$file_content .= ']
';
			}

		} else {
			continue;
		}
	}
}

if (array_key_exists("u", $option)){
	$current_content = file_get_contents($config_file_name);
	$file_content = $current_content . $file_content;
}

if (file_put_contents($config_file_name, $file_content)){
	echo "Content put to : " . $config_file_name . " successfully";
} else {
	echo "Failed to put content to : " . $config_file_name;
}