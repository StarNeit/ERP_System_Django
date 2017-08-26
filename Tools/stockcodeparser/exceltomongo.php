<?php

ini_set('memory_limit', '256M');

$option_text = "i:";
$option_text = "h";
$option = getopt($option_text);

//var_dump($option);

if (array_key_exists("h", $option)){
	exit("php exceltomongo.php -i[input filename]\n");
}

define('EOL',(PHP_SAPI == 'cli') ? PHP_EOL : '<br />');

require dirname(__FILE__) . '/phpexcel/Classes/PHPExcel/IOFactory.php';

// Check if file name is in argument
if (array_key_exists("i", $option)){
	$filename = $option["i"];
} else {
	$filename = "SwarovskiCodes.xlsx";
}

if (!file_exists($filename)) 
{
	exit("File not exist." . EOL);
}

echo "File " , $filename , " exists\n";

/**  Identify the type of $inputFileName  **/
$inputFileType = PHPExcel_IOFactory::identify($filename);
/**  Create a new Reader of the type that has been identified  **/
$objReader = PHPExcel_IOFactory::createReader($inputFileType);
/**  Load $inputFileName to a PHPExcel Object  **/
$objPHPExcel = $objReader->load($filename);

echo "File " , $filename , " loaded\n";

$file_content = "";

class tool_string {
	public $text;
	public $mapping = array();

	function __construct($input_text){
		$this->text = $input_text;
		$this->mapping = $this->build_mapping($input_text,0);
	}

	function get_mapping(){
		return $this->mapping;
	}

	function get_matching_parenthesis($input){
		$open_number = 0;
		$left = 0;
		while (true) {
			$open = strpos($input, "(",$left); 
			$close = strpos($input, ")", $left);
			if ($open < $close and gettype($open) == gettype($close)){
				$open_number++;
				$left = $open+1;
			} else {
				$open_number--;
				$left = $close+1;
			}
			if ($open_number == 0){
				return $close;
			}
		}
		
	}

	function build_mapping($input,$end){

		$end++;

		$mapping_data = array();
		$index = 0;
		while(strlen($input) > 0){
			$start_pos = strpos($input, "(");
			if ($start_pos === 0){
				$matching_end = $this->get_matching_parenthesis($input);
				$left = substr($input, $start_pos+1, $matching_end-1);
				$input = substr($input, $matching_end + 1,strlen($input));
				if (substr($input, 0, 1) == ","){
					$input = substr($input, 1);
				}
				$mapping_data[$index] = $this->build_mapping($left,$end);
				$index++;
			} else {
				if (strpos($input, ",") !== false){
					$left = substr($input, 0, strpos($input, ","));
					$input = substr($input, strpos($input, ",") + 1, strlen($input));
					$mapping_data[$index]["category"] = substr($left, 0, strpos($left, "="));
					$mapping_data[$index]["data"] = substr($left, strpos($left, "=") + 1, strlen($left));
					if (strpos($input, "(") === 0) {
						$matching_end = $this->get_matching_parenthesis($input);
						$left = substr($input, 1, $matching_end - 1);
						$input = substr($input, $matching_end + 1,strlen($input));
						if (strpos($input,",") === 0){
							$input = substr($input, 1);
						}
						$mapping_data[$index]["child"] = $this->build_mapping($left,$end);
					} else {
						$mapping_data[$index]["child"] = NULL;
					}
					$index++;
				} else {
					$mapping_data[$index]["category"] = substr($input, 0, strpos($input, "="));
					$mapping_data[$index]["data"] = substr($input, strpos($input, "=") + 1, strlen($input));
					$mapping_data[$index]["child"] = NULL;
					$input = "";
					$index++;
					return $mapping_data;
				}
			}
		}
		return $mapping_data;
	}

}

// parse_tree(active PHP sheet object, mapping array, parent, level, start from row)
function parse_tree($active, $node, $parent_column, $parent_id, $start, $collection, $level){
	$file_content = -1;

	foreach ($node as $node_key => $node_value) {
		// get columns ID
		$col = explode(":", $node_value["data"]);
		$temp = "";

		for ($row = $start; $row <= $active->getHighestRow(); $row++){

			$key_cell = $active->getCell($col[0].$row);
			$value_cell = $active->getCell($col[1].$row);

			if ($temp != $key_cell->getCalculatedValue()){

				$temp = $key_cell->getCalculatedValue();
				
				$query = array(
					"code" => $temp,
					"group" => $node_value["category"],
					"label" => $value_cell->getCalculatedValue(),
					"parent_id" => $parent_id
				);

				$cursor = $collection->insert($query);
				
				echo "row=". $row .",code=" . $temp .", group=" . $node_value["category"] .
					", label=" . $value_cell->getCalculatedValue() . ", parent=" . $parent_id . 
					", parentcol=". gettype($parent_column) ."\n";

				if (!is_null($node_value["child"])){ 
					if (is_null($parent_column)){
						$parent_column = array();
					}
					$parent_column[$col[0]] = $temp;
					echo "has child sent " . $col[0] . " and " . $temp . "\n";
					$file_content = parse_tree($active, $node_value["child"], $parent_column, $query['_id'], $row, $collection, $level+1);
					if ($file_content < $level){
						return $file_content;
					}
				} else {

					if (!is_null($parent_column)){
						// check if the next row parent column values are still repeating. if not, return $file_content
						$parent_index = 0;
						foreach ($parent_column as $parent_key => $parent_value) {
							echo "compare cell: " . $parent_key . strval($row+1) . "=" . 
									$active->getCell($parent_key. strval($row+1))->getCalculatedValue() .
								 	" == ".$parent_value . ",start=" . $start ."\n";
							if ($parent_value != $active->getCell($parent_key. strval($row+1))->getCalculatedValue()){
								echo "return back to parent index = ".$parent_index."\n";
								return $parent_index;
							}
							$parent_index++;
						}
					}
				}
			} else {
				continue;
			}
		}
	}
	return 1;
}

function drop_db($active, $collection, $node){
	foreach ($node as $node_key => $node_value) {
		// get columns ID
		$col = explode(":", $node_value["data"]);
		$temp = "";

		$query = array("group" => $node_value["category"]);
		$cursor = $collection->findOne($query);

		if (!is_null($cursor)){
			$cursor = $collection->remove($query);
		}

		if (!is_null($node_value["child"])){
			drop_db($active, $collection, $node_value["child"]);
		}
	}
}

// Get setup data from "Tool" sheet
$active = $objPHPExcel->setActiveSheetIndexByName("Tool");
$range = $active->calculateWorksheetDimension();
$data = $active->rangeToArray($range, NULL, true, true);

$index = 0;
// Array containing Target sheet as Key and mapping values as Array
$node = array();

// Read setup data and contructing nested array for parent-child
// Array[SheetIndex][ElementIndex]['code','group','label','child'][ChildElementIndex]['code','group','label','child']
foreach ($data as $row) {
	echo $row[0] . " > " . $row[1] . "\n";
	if ($index > 0){
		if (!is_null($row[1])){
			$tool = new tool_string($row[1]);
			$node[$row[0]] = $tool->get_mapping();
		}
	}
	$index++;
}
// connect to MongoDB
$connection = new MongoClient();
$db = $connection->my_database;
$collection = $db->intramanee_lov;

// loop to remove existing records in MongoDB
foreach ($node as $node_key => $node_value) {
	$active = $objPHPExcel->setActiveSheetIndexByName($node_key);
	drop_db($active, $collection, $node_value);
}

// loop to put records in mongodb
foreach ($node as $node_key => $node_value) {
	$active = $objPHPExcel->setActiveSheetIndexByName($node_key);
	$file_content .= parse_tree($active, $node_value, NULL, NULL, 2, $collection, 0);
}

echo "finished processing\n";